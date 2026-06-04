/**
 * 单链路 Probe
 * - 常驻等待 SIGUSR1
 * - 每次只探测 daemon 指定的一条链路
 * - 顺序固定为 Bandwidth -> Latency
 * - 不做 8x8 矩阵、不做双向往返、不做 warmup
 */

#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <string>
#include <sys/time.h>
#include <unistd.h>
#include <vector>

#include <numa.h>
#include <numaif.h>
#include <signal.h>

#include "acl/acl.h"
#include "acl/acl_rt.h"

#define LATENCY_THRESHOLD_US 35.0
#define BW_BASE_SAME_NUMA    26.5
#define BW_BASE_CROSS_NUMA   21.9
#define BW_DROP_RATIO        0.8
#define LATENCY_BYTES        4096UL
#define LATENCY_ITERS        10
#define BANDWIDTH_BYTES      (128UL * 1024 * 1024)

enum class ProbeDirection {
    H2D,
    D2H,
    UNKNOWN,
};

struct CpuTopology {
    std::vector<int> npus;
    std::vector<int> numas;
};

struct ProbeRequest {
    bool valid = false;
    long long request_id = 0;
    long long trigger_wall_ns = 0;
    std::string source;
    std::string destination;
    ProbeDirection direction = ProbeDirection::UNKNOWN;
    int device_id = -1;
    int numa_id = -1;
    long long window_start_ns = 0;
    long long window_end_ns = 0;
    double window_bw_gbps = 0.0;
};

struct ProbeMetric {
    double value = 0.0;
    double baseline = 0.0;
    bool abnormal = false;
};

std::vector<aclrtContext> g_ctxs;
std::string g_probe_status_file = "./probe.status";
std::string g_probe_request_file = "./probe_request.csv";
CpuTopology g_cpu_map[4];
int g_expected_hccs = 0;
volatile sig_atomic_t g_trigger_probe = 0;

static inline uint64_t read_cntvct(void) {
    uint64_t val;
    __asm__ __volatile__("mrs %0, cntvct_el0" : "=r"(val));
    return val;
}

static inline uint64_t read_cntfrq(void) {
    uint64_t val;
    __asm__ __volatile__("mrs %0, cntfrq_el0" : "=r"(val));
    return val;
}

static inline double ticks_to_us(uint64_t ticks, uint64_t freq) {
    return static_cast<double>(ticks) * 1000000.0 / static_cast<double>(freq);
}

bool check_acl(aclError err, const char* expr) {
    if (err == ACL_ERROR_NONE) return true;
    fprintf(stderr, "[ACL] %s failed: %d\n", expr, static_cast<int>(err));
    return false;
}

std::vector<std::string> split_csv_line(const std::string& line) {
    std::vector<std::string> parts;
    std::string cur;
    for (char c : line) {
        if (c == ',') {
            parts.push_back(cur);
            cur.clear();
        } else {
            cur.push_back(c);
        }
    }
    parts.push_back(cur);
    return parts;
}

const char* direction_to_string(ProbeDirection direction) {
    switch (direction) {
        case ProbeDirection::H2D: return "H2D";
        case ProbeDirection::D2H: return "D2H";
        default: return "UNKNOWN";
    }
}

ProbeDirection parse_direction(const std::string& text) {
    if (text == "H2D") return ProbeDirection::H2D;
    if (text == "D2H") return ProbeDirection::D2H;
    return ProbeDirection::UNKNOWN;
}

int get_cpu_id_by_npu(int npu_id) {
    for (int i = 0; i < 4; ++i) {
        for (int n : g_cpu_map[i].npus) {
            if (n == npu_id) return i;
        }
    }
    return -1;
}

int get_cpu_id_by_numa(int numa_id) {
    for (int i = 0; i < 4; ++i) {
        for (int n : g_cpu_map[i].numas) {
            if (n == numa_id) return i;
        }
    }
    return -1;
}

bool is_same_numa_group(int npu_id, int numa_id) {
    return get_cpu_id_by_npu(npu_id) == get_cpu_id_by_numa(numa_id);
}

void init_topology_910b() {
    g_cpu_map[0] = {{4, 5}, {0, 1}};
    g_cpu_map[1] = {{6, 7}, {2, 3}};
    g_cpu_map[2] = {{2, 3}, {4, 5}};
    g_cpu_map[3] = {{0, 1}, {6, 7}};
    g_expected_hccs = 56;
    printf("[Info] Detected 910B Series. Expected HCCS: %d\n", g_expected_hccs);
}

void init_topology_910a() {
    g_cpu_map[0] = {{3, 7}, {0, 1}};
    g_cpu_map[1] = {{2, 6}, {2, 3}};
    g_cpu_map[2] = {{1, 5}, {4, 5}};
    g_cpu_map[3] = {{0, 4}, {6, 7}};
    g_expected_hccs = 24;
    printf("[Info] Detected 910A Series. Expected HCCS: %d\n", g_expected_hccs);
}

void detect_soc_and_init_topology() {
    const char* soc_name = aclrtGetSocName();
    if (!soc_name) {
        fprintf(stderr, "[Warning] Failed to get SoC name. Defaulting to 910A.\n");
        init_topology_910a();
        return;
    }
    printf("[Init] SoC Name: %s\n", soc_name);
    std::string name(soc_name);
    if (name.find("Ascend910B1") != std::string::npos ||
        name.find("Ascend910B2") != std::string::npos ||
        name.find("Ascend910B3") != std::string::npos ||
        name.find("Ascend910B4") != std::string::npos) {
        init_topology_910b();
    } else {
        init_topology_910a();
    }
}

void check_hccs_topology() {
    printf("[Init] Checking NPU Topology via 'npu-smi info -t topo'...\n");
    FILE* pipe = popen("npu-smi info -t topo", "r");
    if (!pipe) {
        fprintf(stderr, "[Error] Failed to execute npu-smi command.\n");
        return;
    }

    char buffer[1024];
    int hccs_count = 0;
    while (fgets(buffer, sizeof(buffer), pipe) != nullptr) {
        if (strncmp(buffer, "NPU", 3) == 0 && std::isdigit(buffer[3])) {
            std::string line(buffer);
            size_t pos = 0;
            while ((pos = line.find("HCCS", pos)) != std::string::npos) {
                ++hccs_count;
                pos += 4;
            }
        }
    }
    pclose(pipe);

    if (hccs_count == g_expected_hccs) {
        printf("\033[1;32m[Success] NPU之间HCCS链路正常 \033[0m\n");
    } else {
        printf("\033[1;31m[Error] NPU之间HCCS链路异常! 预期: %d, 实际: %d\033[0m\n", g_expected_hccs, hccs_count);
    }
    printf("----------------------------------------------------------------\n");
}

void write_probe_state(const char* state) {
    std::ofstream out(g_probe_status_file, std::ios::out | std::ios::trunc);
    if (!out.is_open()) return;
    out << state << "\n";
    out.flush();
}

void signal_handler(int signum) {
    if (signum == SIGUSR1) {
        g_trigger_probe = 1;
    }
}

void print_system_time() {
    struct timeval tv;
    gettimeofday(&tv, nullptr);
    struct tm* tm_info = localtime(&tv.tv_sec);
    char time_str[32];
    strftime(time_str, sizeof(time_str), "%Y-%m-%d %H:%M:%S", tm_info);
    printf("[System Time]: %s.%03ld\n", time_str, tv.tv_usec / 1000);
}

void print_request_summary(const ProbeRequest& request) {
    printf("[ProbeTarget] Source=%s Destination=%s Direction=%s Device=%d NUMA=%d\n",
           request.source.c_str(),
           request.destination.c_str(),
           direction_to_string(request.direction),
           request.device_id,
           request.numa_id);
    printf("[ProbeTarget] WindowNs=%lld-%lld WindowBW=%.2f GB/s TriggerWallNs=%lld\n",
           request.window_start_ns,
           request.window_end_ns,
           request.window_bw_gbps,
           request.trigger_wall_ns);
}

ProbeRequest load_probe_request() {
    ProbeRequest request;
    std::ifstream in(g_probe_request_file);
    if (!in.is_open()) {
        fprintf(stderr, "[Probe] Failed to open request file: %s\n", g_probe_request_file.c_str());
        return request;
    }

    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty()) {
            auto cols = split_csv_line(line);
            if (cols.size() < 10) continue;
            try {
                request.request_id = std::stoll(cols[0]);
                request.trigger_wall_ns = std::stoll(cols[1]);
                request.source = cols[2];
                request.destination = cols[3];
                request.direction = parse_direction(cols[4]);
                request.device_id = std::stoi(cols[5]);
                request.numa_id = std::stoi(cols[6]);
                request.window_start_ns = std::stoll(cols[7]);
                request.window_end_ns = std::stoll(cols[8]);
                request.window_bw_gbps = std::stod(cols[9]);
                request.valid = request.direction != ProbeDirection::UNKNOWN &&
                                request.device_id >= 0 &&
                                request.numa_id >= 0;
            } catch (...) {
                request.valid = false;
            }
        }
    }
    return request;
}

int bind_to_numa_node(int node) {
    if (node < 0 || numa_available() < 0) return 0;
    struct bitmask* memmask = numa_allocate_nodemask();
    numa_bitmask_clearall(memmask);
    numa_bitmask_setbit(memmask, node);
    set_mempolicy(MPOL_BIND, memmask->maskp, memmask->size + 1);
    numa_free_nodemask(memmask);
    return 0;
}

bool prepare_buffers(size_t bytes, void** host_ptr, void** dev_ptr, ProbeDirection direction) {
    *host_ptr = nullptr;
    *dev_ptr = nullptr;
    if (!check_acl(aclrtMallocHost(host_ptr, bytes), "aclrtMallocHost")) return false;
    std::memset(*host_ptr, 1, bytes);
    if (!check_acl(aclrtMalloc(dev_ptr, bytes, ACL_MEM_MALLOC_NORMAL_ONLY), "aclrtMalloc")) {
        aclrtFreeHost(*host_ptr);
        *host_ptr = nullptr;
        return false;
    }
    if (direction == ProbeDirection::D2H) {
        if (!check_acl(aclrtMemcpy(*dev_ptr, bytes, *host_ptr, bytes, ACL_MEMCPY_HOST_TO_DEVICE), "prime d2h buffer")) {
            aclrtFree(*dev_ptr);
            aclrtFreeHost(*host_ptr);
            *dev_ptr = nullptr;
            *host_ptr = nullptr;
            return false;
        }
    }
    return true;
}

void release_buffers(void* host_ptr, void* dev_ptr) {
    if (dev_ptr) aclrtFree(dev_ptr);
    if (host_ptr) aclrtFreeHost(host_ptr);
}

bool run_one_copy(ProbeDirection direction, void* host_ptr, void* dev_ptr, size_t bytes) {
    if (direction == ProbeDirection::H2D) {
        return check_acl(aclrtMemcpy(dev_ptr, bytes, host_ptr, bytes, ACL_MEMCPY_HOST_TO_DEVICE), "aclrtMemcpy H2D");
    }
    if (direction == ProbeDirection::D2H) {
        return check_acl(aclrtMemcpy(host_ptr, bytes, dev_ptr, bytes, ACL_MEMCPY_DEVICE_TO_HOST), "aclrtMemcpy D2H");
    }
    return false;
}

ProbeMetric measure_bandwidth(const ProbeRequest& request) {
    ProbeMetric metric;
    metric.baseline = is_same_numa_group(request.device_id, request.numa_id) ? BW_BASE_SAME_NUMA : BW_BASE_CROSS_NUMA;
    if (!check_acl(aclrtSetCurrentContext(g_ctxs[request.device_id]), "aclrtSetCurrentContext")) return metric;
    bind_to_numa_node(request.numa_id);

    void* host_ptr = nullptr;
    void* dev_ptr = nullptr;
    if (!prepare_buffers(BANDWIDTH_BYTES, &host_ptr, &dev_ptr, request.direction)) return metric;

    static uint64_t freq = 0;
    if (freq == 0) freq = read_cntfrq();
    check_acl(aclrtSynchronizeDevice(), "aclrtSynchronizeDevice before BW");
    uint64_t start_tick = read_cntvct();
    bool ok = run_one_copy(request.direction, host_ptr, dev_ptr, BANDWIDTH_BYTES);
    check_acl(aclrtSynchronizeDevice(), "aclrtSynchronizeDevice after BW");
    uint64_t end_tick = read_cntvct();

    if (ok) {
        double elapsed_us = ticks_to_us(end_tick - start_tick, freq);
        if (elapsed_us > 0.0) {
            metric.value = static_cast<double>(BANDWIDTH_BYTES) / 1e9 / (elapsed_us / 1e6);
            metric.abnormal = metric.value < (metric.baseline * BW_DROP_RATIO);
        }
    }

    release_buffers(host_ptr, dev_ptr);
    return metric;
}

ProbeMetric measure_latency(const ProbeRequest& request) {
    ProbeMetric metric;
    metric.baseline = LATENCY_THRESHOLD_US;
    if (!check_acl(aclrtSetCurrentContext(g_ctxs[request.device_id]), "aclrtSetCurrentContext")) return metric;
    bind_to_numa_node(request.numa_id);

    void* host_ptr = nullptr;
    void* dev_ptr = nullptr;
    if (!prepare_buffers(LATENCY_BYTES, &host_ptr, &dev_ptr, request.direction)) return metric;

    static uint64_t freq = 0;
    if (freq == 0) freq = read_cntfrq();

    double total_us = 0.0;
    for (int i = 0; i < LATENCY_ITERS; ++i) {
        check_acl(aclrtSynchronizeDevice(), "aclrtSynchronizeDevice before LAT");
        uint64_t start_tick = read_cntvct();
        bool ok = run_one_copy(request.direction, host_ptr, dev_ptr, LATENCY_BYTES);
        check_acl(aclrtSynchronizeDevice(), "aclrtSynchronizeDevice after LAT");
        uint64_t end_tick = read_cntvct();
        if (!ok) {
            total_us = 0.0;
            break;
        }
        total_us += ticks_to_us(end_tick - start_tick, freq);
    }

    if (total_us > 0.0) {
        metric.value = total_us / LATENCY_ITERS;
        metric.abnormal = metric.value > metric.baseline;
    }

    release_buffers(host_ptr, dev_ptr);
    return metric;
}

void print_bandwidth_report(long long loop_cnt, const ProbeRequest& request, const ProbeMetric& metric) {
    printf("\n>>> 异常探测报告 (Loop %lld, Type: Bandwidth) <<<\n", loop_cnt);
    print_system_time();
    print_request_summary(request);
    printf("[测量结果] Bandwidth=%.2f GB/s Baseline=%.2f GB/s Threshold=%.2f GB/s Bytes=%.2f MB\n",
           metric.value,
           metric.baseline,
           metric.baseline * BW_DROP_RATIO,
           static_cast<double>(BANDWIDTH_BYTES) / (1024.0 * 1024.0));
    printf("\n[故障分析]:\n");
    if (metric.abnormal) {
        printf("- [链路带宽异常] %s -> %s 单链路带宽不足。\n",
               request.source.c_str(),
               request.destination.c_str());
        printf("[汇总] 实际探测到异常次数: 1\n");
    } else {
        printf("- 未探测到带宽异常。\n");
        printf("[汇总] 实际探测到异常次数: 0\n");
    }
    printf("----------------------------------------------------------------\n");
}

void print_latency_report(long long loop_cnt, const ProbeRequest& request, const ProbeMetric& metric) {
    printf("\n>>> 异常探测报告 (Loop %lld, Type: Latency) <<<\n", loop_cnt);
    print_system_time();
    print_request_summary(request);
    printf("[测量结果] Latency=%.2f us Threshold=%.2f us Bytes=%lu B Iters=%d\n",
           metric.value,
           metric.baseline,
           static_cast<unsigned long>(LATENCY_BYTES),
           LATENCY_ITERS);
    printf("\n[故障分析]:\n");
    if (metric.abnormal) {
        printf("- [链路时延异常] %s -> %s 单链路时延偏高。\n",
               request.source.c_str(),
               request.destination.c_str());
        printf("[汇总] 实际探测到异常次数: 1\n");
    } else {
        printf("- 未探测到时延异常。\n");
        printf("[汇总] 实际探测到异常次数: 0\n");
    }
    printf("----------------------------------------------------------------\n");
}

bool init_contexts() {
    if (!check_acl(aclInit(nullptr), "aclInit")) return false;
    if (numa_available() < 0) {
        fprintf(stderr, "[Probe] NUMA is not available.\n");
        return false;
    }
    g_ctxs.resize(8);
    for (int i = 0; i < 8; ++i) {
        if (!check_acl(aclrtSetDevice(i), "aclrtSetDevice")) return false;
        if (!check_acl(aclrtCreateContext(&g_ctxs[i], i), "aclrtCreateContext")) return false;
    }
    return true;
}

int main() {
    const char* status_path = std::getenv("PROBE_STATUS_FILE");
    if (status_path && status_path[0] != '\0') g_probe_status_file = status_path;
    const char* request_path = std::getenv("PROBE_REQUEST_FILE");
    if (request_path && request_path[0] != '\0') g_probe_request_file = request_path;

    signal(SIGUSR1, signal_handler);

    if (!init_contexts()) return 1;
    detect_soc_and_init_topology();
    check_hccs_topology();

    printf("[Init] Probe Status File: %s\n", g_probe_status_file.c_str());
    printf("[Init] Probe Request File: %s\n", g_probe_request_file.c_str());
    printf("[Init] Probe Mode: single-link only, bw->lat, no warmup, no bidirectional, no 8x8 matrix\n");
    write_probe_state("idle");
    printf("[ProbeState] idle\n");
    printf("Monitor Started. Waiting for SIGUSR1 to probe...\n");

    long long loop_cnt = 0;
    while (true) {
        if (g_trigger_probe) {
            g_trigger_probe = 0;
            ++loop_cnt;
            write_probe_state("busy");
            printf("[ProbeState] busy\n");
            printf("[Probe] Triggered by Signal (Loop %lld)\n", loop_cnt);

            ProbeRequest request = load_probe_request();
            if (!request.valid) {
                fprintf(stderr, "[Probe] Invalid request. Skip loop %lld.\n", loop_cnt);
            } else {
                ProbeMetric bandwidth_metric = measure_bandwidth(request);
                print_bandwidth_report(loop_cnt, request, bandwidth_metric);
                ProbeMetric latency_metric = measure_latency(request);
                print_latency_report(loop_cnt, request, latency_metric);
            }

            printf("[Probe] Finished.\n");
            write_probe_state("idle");
            printf("[ProbeState] idle\n");
        }
        usleep(1000);
    }
    return 0;
}
