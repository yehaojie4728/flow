# 01. aarch64 + 910A + EulerOS/openEuler 环境配置

---

## 1. 基础系统检查

```bash
uname -a
uname -m
cat /etc/os-release
whoami
id
```

期望：

```text
uname -m = aarch64
```

---

## 2. 检查 Ascend/CANN

```bash
ls /usr/local/Ascend 2>/dev/null || true
find /usr/local/Ascend -name "set_env.sh" 2>/dev/null | head
find /usr/local/Ascend -name "setenv.bash" 2>/dev/null | head
find /usr/local/Ascend -name "libascendcl.so*" 2>/dev/null | head
```

加载环境：

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh 2>/dev/null || true
source /usr/local/Ascend/latest/bin/setenv.bash 2>/dev/null || true
```

检查 AscendCL 符号：

```bash
ASCENDCL_SO=$(find /usr/local/Ascend -name "libascendcl.so*" 2>/dev/null | head -n 1)
echo "$ASCENDCL_SO"

if [ -n "$ASCENDCL_SO" ]; then
  nm -D "$ASCENDCL_SO" 2>/dev/null | grep -E "aclrtMemcpy|aclrtMemcpyAsync|aclrtSynchronizeStream|aclrtSetDevice" | head -n 50
fi
```

---

## 3. 检查 eBPF/uprobe 支持

```bash
grep -E "CONFIG_BPF|CONFIG_BPF_SYSCALL|CONFIG_UPROBE_EVENTS|CONFIG_KPROBES|CONFIG_BPF_EVENTS" /boot/config-$(uname -r) 2>/dev/null || true
zcat /proc/config.gz 2>/dev/null | grep -E "CONFIG_BPF|CONFIG_BPF_SYSCALL|CONFIG_UPROBE_EVENTS|CONFIG_KPROBES|CONFIG_BPF_EVENTS" || true
```

检查 tracefs：

```bash
ls /sys/kernel/tracing 2>/dev/null || true
ls /sys/kernel/debug/tracing 2>/dev/null || true
ls /sys/kernel/tracing/uprobe_events 2>/dev/null || true
ls /sys/kernel/debug/tracing/uprobe_events 2>/dev/null || true
```

---

## 4. 安装系统依赖

优先 `dnf`：

```bash
dnf install -y git curl wget tar gzip unzip rsync tree jq make cmake gcc gcc-c++   python3 python3-pip python3-devel   nodejs npm   clang llvm elfutils-libelf-devel   libbpf libbpf-devel bpftool   kernel-devel-$(uname -r) kernel-headers-$(uname -r)   perf strace ltrace
```

如果没有 `dnf`：

```bash
yum install -y git curl wget tar gzip unzip rsync tree jq make cmake gcc gcc-c++   python3 python3-pip python3-devel   nodejs npm   clang llvm elfutils-libelf-devel   libbpf libbpf-devel bpftool   kernel-devel-$(uname -r) kernel-headers-$(uname -r)   perf strace ltrace
```

---

## 5. 安装 Miniforge

```bash
cd ~
curl -L -o Miniforge3-Linux-aarch64.sh   https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-aarch64.sh

bash Miniforge3-Linux-aarch64.sh -b -p "$HOME/miniforge3"

source "$HOME/miniforge3/bin/activate"
conda init bash
source ~/.bashrc
```

创建环境：

```bash
conda create -y -n flowgap python=3.11
conda activate flowgap
```

安装 Python 依赖：

```bash
conda install -y -c conda-forge   numpy pandas scipy scikit-learn statsmodels pyarrow matplotlib pyyaml tqdm joblib   ipython pytest rich typer
```

安装 uv 和可选包：

```bash
python -m pip install -U pip
python -m pip install uv
python -m pip install simpy pymoo
python -m pip install aeon || echo "aeon install failed; continue without aeon for now"
```

验证：

```bash
python - <<'PY'
import sys
print(sys.version)
import numpy, pandas, scipy, sklearn, statsmodels, matplotlib, pyarrow
print("FlowGap basic Python stack OK")
PY
```

---

## 6. GitHub CLI gh

```bash
gh --version || true
gh skill --help || true
```

如果没有 gh skill，可按你的环境安装 GitHub CLI v2.90.0+，或使用 `.agent/skills/` 手动复制方案。

---

## 7. 成功标志

```bash
uname -m
python - <<'PY'
import numpy, pandas, sklearn, statsmodels, pyarrow
print("python stack ok")
PY
gh --version || true
uv --version || true
```
