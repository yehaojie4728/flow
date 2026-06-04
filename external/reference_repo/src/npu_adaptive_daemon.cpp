#include <cerrno>
#include <cctype>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fstream>
#include <getopt.h>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include <sys/stat.h>
#include <sys/time.h>
#include <unistd.h>

double get_time_sec() {
    struct timeval tv;
    gettimeofday(&tv, nullptr);
    return tv.tv_sec + tv.tv_usec / 1e6;
}

long long get_wall_time_ns() {
    struct timeval tv;
    gettimeofday(&tv, nullptr);
    return static_cast<long long>(tv.tv_sec) * 1000000000LL +
           static_cast<long long>(tv.tv_usec) * 1000LL;
}

void print_usage(const char* prog_name) {
    std::cerr
        << "Usage: " << prog_name << " [options]\n"
        << "Options:\n"
        << "  --log-file <path>         Path to trace log file\n"
        << "  --benchmark-cmd <cmd>     Compatibility option (unused)\n"
        << "  --probe-pid-file <path>   Probe PID file path\n"
        << "  --probe-status-file <path> Probe busy/idle state file path\n"
        << "  --probe-request-file <path> Probe request CSV path\n"
        << "  --trigger-log-file <path> Trigger metadata CSV path\n"
        << "  --low <mbps>              Low threshold in MB/s\n"
        << "  --high <mbps>             High threshold in MB/s\n"
        << "  --cooldown <sec>          Cooldown period in seconds\n"
        << "  --help                    Show this help message\n";
}

bool read_pid_from_file(const std::string& pid_file, pid_t& pid_out) {
    std::ifstream in(pid_file);
    if (!in.is_open()) return false;
    std::string line;
    if (!std::getline(in, line)) return false;
    if (line.empty()) return false;
    try {
        long long pid_ll = std::stoll(line);
        if (pid_ll <= 0) return false;
        pid_out = static_cast<pid_t>(pid_ll);
        return true;
    } catch (...) {
        return false;
    }
}

std::string read_probe_state(const std::string& state_file) {
    if (state_file.empty()) return "";
    std::ifstream in(state_file);
    if (!in.is_open()) return "";
    std::string line;
    if (!std::getline(in, line)) return "";
    return line;
}

bool parse_host_numa(const std::string& text, int& numa_out) {
    const std::string prefix = "Host(NUMA ";
    if (text.rfind(prefix, 0) != 0) return false;
    size_t end = text.find(')', prefix.size());
    if (end == std::string::npos) return false;
    try {
        numa_out = std::stoi(text.substr(prefix.size(), end - prefix.size()));
        return true;
    } catch (...) {
        return false;
    }
}

bool parse_npu_id(const std::string& text, int& npu_out) {
    const std::string prefix = "NPU ";
    if (text.rfind(prefix, 0) != 0) return false;
    try {
        npu_out = std::stoi(text.substr(prefix.size()));
        return true;
    } catch (...) {
        return false;
    }
}

bool build_probe_request(
    const std::string& src,
    const std::string& dst,
    int& device_id,
    int& numa_id,
    std::string& direction
) {
    int src_numa = -1;
    int dst_numa = -1;
    int src_npu = -1;
    int dst_npu = -1;
    bool src_is_host = parse_host_numa(src, src_numa);
    bool dst_is_host = parse_host_numa(dst, dst_numa);
    bool src_is_npu = parse_npu_id(src, src_npu);
    bool dst_is_npu = parse_npu_id(dst, dst_npu);
    if (src_is_host && dst_is_npu) {
        device_id = dst_npu;
        numa_id = src_numa;
        direction = "H2D";
        return true;
    }
    if (src_is_npu && dst_is_host) {
        device_id = src_npu;
        numa_id = dst_numa;
        direction = "D2H";
        return true;
    }
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

std::string first_token(const std::string& cmd) {
    size_t i = 0;
    while (i < cmd.size() && std::isspace(static_cast<unsigned char>(cmd[i]))) i++;
    if (i >= cmd.size()) return "";
    if (cmd[i] == '\'' || cmd[i] == '"') {
        char q = cmd[i++];
        size_t j = i;
        while (j < cmd.size() && cmd[j] != q) j++;
        return cmd.substr(i, j - i);
    }
    size_t j = i;
    while (j < cmd.size() && !std::isspace(static_cast<unsigned char>(cmd[j]))) j++;
    return cmd.substr(i, j - i);
}

bool is_digits(const std::string& s) {
    if (s.empty()) return false;
    for (char c : s) {
        if (c < '0' || c > '9') return false;
    }
    return true;
}

bool find_pid_by_cmdline_token(const std::string& token, pid_t& pid_out) {
    if (token.empty()) return false;
    DIR* dir = opendir("/proc");
    if (!dir) return false;
    struct dirent* ent = nullptr;
    pid_t best = -1;
    while ((ent = readdir(dir)) != nullptr) {
        std::string name(ent->d_name);
        if (!is_digits(name)) continue;
        std::string cmdline_path = "/proc/" + name + "/cmdline";
        std::ifstream in(cmdline_path, std::ios::in | std::ios::binary);
        if (!in.is_open()) continue;
        std::string cmdline((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        if (cmdline.empty()) continue;
        std::string normalized = cmdline;
        for (char& c : normalized) {
            if (c == '\0') c = ' ';
        }
        if (normalized.find(token) != std::string::npos) {
            pid_t pid = static_cast<pid_t>(std::stoi(name));
            if (pid > best) best = pid;
        }
    }
    closedir(dir);
    if (best > 0) {
        pid_out = best;
        return true;
    }
    return false;
}

int main(int argc, char* argv[]) {
    std::string log_file = "./runs/agg/aclrtMemcpy_numa_trace.log";
    std::string benchmark_cmd = "./probe/build/memcpy_benchmark";
    std::string probe_pid_file = "./logs/runtime/probe.pid";
    std::string probe_status_file = "./logs/runtime/probe.status";
    std::string probe_request_file = "./logs/runtime/probe_request.csv";
    std::string trigger_log_file = "./runs/agg/probe_trigger_windows.csv";
    double low_mbps = 100.0;
    double high_mbps = 5000.0;
    double cooldown = 10.0;

    static struct option long_options[] = {
        {"log-file", required_argument, nullptr, 'l'},
        {"benchmark-cmd", required_argument, nullptr, 'b'},
        {"probe-pid-file", required_argument, nullptr, 'p'},
        {"probe-status-file", required_argument, nullptr, 's'},
        {"probe-request-file", required_argument, nullptr, 'r'},
        {"trigger-log-file", required_argument, nullptr, 't'},
        {"low", required_argument, nullptr, 'L'},
        {"high", required_argument, nullptr, 'H'},
        {"cooldown", required_argument, nullptr, 'c'},
        {"help", no_argument, nullptr, 'h'},
        {nullptr, 0, nullptr, 0}
    };

    int opt;
    int option_index = 0;
    while ((opt = getopt_long(argc, argv, "l:b:p:s:r:t:L:H:c:h", long_options, &option_index)) != -1) {
        switch (opt) {
            case 'l': log_file = optarg; break;
            case 'b': benchmark_cmd = optarg; break;
            case 'p': probe_pid_file = optarg; break;
            case 's': probe_status_file = optarg; break;
            case 'r': probe_request_file = optarg; break;
            case 't': trigger_log_file = optarg; break;
            case 'L': low_mbps = std::stod(optarg); break;
            case 'H': high_mbps = std::stod(optarg); break;
            case 'c': cooldown = std::stod(optarg); break;
            case 'h': print_usage(argv[0]); return 0;
            default: print_usage(argv[0]); return 1;
        }
    }

    std::cout << "[Adaptive Daemon] Starting..." << std::endl;
    std::cout << "[Adaptive Daemon] Monitoring Log: " << log_file << std::endl;
    std::cout << "[Adaptive Daemon] Logic: Probe if " << low_mbps << " < Rate < " << high_mbps
              << " MB/s (Abnormal Range)" << std::endl;
    std::cout << "[Adaptive Daemon] Probe Command (compat): " << benchmark_cmd << std::endl;
    std::cout << "[Adaptive Daemon] Probe PID File: " << probe_pid_file << std::endl;
    std::cout << "[Adaptive Daemon] Probe Status File: " << probe_status_file << std::endl;
    std::cout << "[Adaptive Daemon] Probe Request File: " << probe_request_file << std::endl;
    std::cout << "[Adaptive Daemon] Trigger Log File: " << trigger_log_file << std::endl;
    std::string probe_cmd_token = first_token(benchmark_cmd);
    long long trigger_seq = 0;

    {
        struct stat st {};
        if (stat(trigger_log_file.c_str(), &st) != 0) {
            std::ofstream out(trigger_log_file);
            if (out.is_open()) {
                out << "trigger_seq,trigger_wall_ns,window_start_ns,window_end_ns,source,destination,bytes_mb,bandwidth_gbps\n";
            }
        }
    }

    std::ifstream file(log_file);
    while (!file.is_open()) {
        std::cerr << "[Adaptive Daemon] Waiting for log file to be created: " << log_file << "..." << std::endl;
        sleep(2);
        file.open(log_file);
    }

    double window_start = get_time_sec();
    double current_mb_sum = 0.0;
    double last_probe_time = 0.0;
    std::string line;
    line.reserve(512);
    bool is_live = false;
    bool seen_data = false;
    bool is_agg_format = false;

    while (true) {
        std::streampos current_pos = file.tellg();
        if (std::getline(file, line)) {
            if (line.empty()) continue;
            if (line.rfind("WindowStart_ns,WindowEnd_ns", 0) == 0) {
                is_agg_format = true;
                continue;
            }
            if (line.rfind("PID,TID,", 0) == 0) {
                is_agg_format = false;
                continue;
            }

            if (is_agg_format) {
                auto cols = split_csv_line(line);
                if (cols.size() >= 6) {
                    char* end_ptr = nullptr;
                    double bw_gbps = std::strtod(cols[5].c_str(), &end_ptr);
                    if (end_ptr != cols[5].c_str()) {
                        seen_data = true;
                        if (!is_live) is_live = true;
                        double rate_mbps = bw_gbps * 1000.0;
                        double now = get_time_sec();
                        bool is_abnormal = (rate_mbps > low_mbps) && (rate_mbps < high_mbps);
                        const std::string& window_start_ns = cols[0];
                        const std::string& window_end_ns = cols[1];
                        const std::string& src = cols[2];
                        const std::string& dst = cols[3];
                        const std::string& bytes_mb = cols[4];
                        if (is_live && is_abnormal && (now - last_probe_time > cooldown)) {
                            std::string probe_state = read_probe_state(probe_status_file);
                            if (probe_state == "busy") {
                                std::cout << "[Adaptive Daemon] Link Rate: " << rate_mbps
                                          << " MB/s (Abnormal Range), but probe is busy. Skip SIGUSR1." << std::endl;
                                last_probe_time = now;
                                continue;
                            }
                            int device_id = -1;
                            int numa_id = -1;
                            std::string direction;
                            if (!build_probe_request(src, dst, device_id, numa_id, direction)) {
                                std::cout << "[Adaptive Daemon] Link Rate: " << rate_mbps
                                          << " MB/s (Abnormal Range), but direction is unsupported for probe: "
                                          << src << " -> " << dst << std::endl;
                                last_probe_time = now;
                                continue;
                            }
                            std::cout << "[Adaptive Daemon] Link Rate: " << rate_mbps
                                      << " MB/s (Abnormal Range). Triggering Probe via SIGUSR1..." << std::endl;
                            {
                                std::ofstream request_out(probe_request_file, std::ios::out | std::ios::trunc);
                                if (request_out.is_open()) {
                                    request_out << (trigger_seq + 1) << "," << get_wall_time_ns() << ","
                                                << src << "," << dst << "," << direction << ","
                                                << device_id << "," << numa_id << ","
                                                << window_start_ns << "," << window_end_ns << ","
                                                << cols[5] << "\n";
                                }
                            }
                            pid_t probe_pid = -1;
                            bool pid_ok = read_pid_from_file(probe_pid_file, probe_pid);
                            if (!pid_ok && find_pid_by_cmdline_token(probe_cmd_token, probe_pid)) {
                                pid_ok = true;
                            }
                            if (!pid_ok) {
                                std::cerr << "[Adaptive Daemon] Warning: Failed to read probe pid from "
                                          << probe_pid_file << std::endl;
                            } else if (kill(probe_pid, SIGUSR1) != 0) {
                                if (errno == ESRCH && find_pid_by_cmdline_token(probe_cmd_token, probe_pid) &&
                                    kill(probe_pid, SIGUSR1) == 0) {
                                    std::cout << "[Adaptive Daemon] Signal sent successfully to pid "
                                              << probe_pid << " (resolved by cmdline)." << std::endl;
                                } else {
                                    std::cerr << "[Adaptive Daemon] Warning: Failed to send SIGUSR1 to pid "
                                              << probe_pid << ", errno=" << errno << " (" << std::strerror(errno) << ")"
                                              << std::endl;
                                }
                            } else {
                                std::cout << "[Adaptive Daemon] Signal sent successfully to pid "
                                          << probe_pid << "." << std::endl;
                                ++trigger_seq;
                                std::ofstream out(trigger_log_file, std::ios::app);
                                if (out.is_open()) {
                                    out << trigger_seq << "," << get_wall_time_ns() << ","
                                        << window_start_ns << "," << window_end_ns << ","
                                        << src << "," << dst << "," << bytes_mb << ","
                                        << cols[5] << "\n";
                                }
                            }
                            last_probe_time = get_time_sec();
                        }
                    }
                }
            } else {
                const char* ptr = line.c_str();
                int comma_count = 0;
                const char* size_start = nullptr;
                while (*ptr) {
                    if (*ptr == ',') {
                        comma_count++;
                        if (comma_count == 4) {
                            size_start = ptr + 1;
                            break;
                        }
                    }
                    ptr++;
                }

                if (size_start && *size_start) {
                    char* end_ptr = nullptr;
                    double size_mb = std::strtod(size_start, &end_ptr);
                    if (end_ptr != size_start) {
                        seen_data = true;
                        if (!is_live) is_live = true;
                        current_mb_sum += size_mb;
                    }
                }

                double now = get_time_sec();
                if (now - window_start >= 1.0) {
                    double duration = now - window_start;
                    double rate_mbps = current_mb_sum / duration;
                    bool is_abnormal = (rate_mbps > low_mbps) && (rate_mbps < high_mbps);

                    if (is_live && is_abnormal && (now - last_probe_time > cooldown)) {
                        std::cout << "[Adaptive Daemon] Traffic Rate: " << rate_mbps
                                  << " MB/s (Abnormal Range). Triggering Probe via SIGUSR1..." << std::endl;

                        pid_t probe_pid = -1;
                        bool pid_ok = read_pid_from_file(probe_pid_file, probe_pid);
                        if (!pid_ok && find_pid_by_cmdline_token(probe_cmd_token, probe_pid)) {
                            pid_ok = true;
                        }
                        if (!pid_ok) {
                            std::cerr << "[Adaptive Daemon] Warning: Failed to read probe pid from "
                                      << probe_pid_file << std::endl;
                        } else if (kill(probe_pid, SIGUSR1) != 0) {
                            if (errno == ESRCH && find_pid_by_cmdline_token(probe_cmd_token, probe_pid) &&
                                kill(probe_pid, SIGUSR1) == 0) {
                                std::cout << "[Adaptive Daemon] Signal sent successfully to pid "
                                          << probe_pid << " (resolved by cmdline)." << std::endl;
                            } else {
                                std::cerr << "[Adaptive Daemon] Warning: Failed to send SIGUSR1 to pid "
                                          << probe_pid << ", errno=" << errno << " (" << std::strerror(errno) << ")"
                                          << std::endl;
                            }
                        } else {
                            std::cout << "[Adaptive Daemon] Signal sent successfully to pid "
                                      << probe_pid << "." << std::endl;
                        }
                        last_probe_time = get_time_sec();
                    }

                    current_mb_sum = 0.0;
                    window_start = now;
                }
            }
        } else {
            file.clear();
            file.seekg(current_pos);
            usleep(1000);
        }
    }

    return 0;
}
