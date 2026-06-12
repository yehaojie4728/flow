#!/usr/bin/env bash
# ============================================================================
# inject_hccs_fault.sh — Inject HCCS link bandwidth degradation
#
# 用途: 在训练中途限流一条 HCCS 链路,模拟硬件故障/拥塞
# 原理: 使用 tc (traffic control) 限制指定网络接口带宽
#
# 要求: root 权限, iproute2 工具 (tc 命令)
#
# 用法:
#   bash inject_hccs_fault.sh start <interface> <bandwidth_limit>
#   bash inject_hccs_fault.sh stop <interface>
#
# 示例:
#   bash inject_hccs_fault.sh start hccs0 5gbit   # 限流到 5 Gbps
#   bash inject_hccs_fault.sh stop hccs0          # 恢复正常
# ============================================================================

set -euo pipefail

ACTION="${1:-}"
INTERFACE="${2:-}"
BANDWIDTH_LIMIT="${3:-}"

usage() {
    cat <<EOF
用法:
  $0 start <interface> <bandwidth_limit>
      启动故障注入,将指定接口限流到指定带宽
      示例: $0 start hccs0 5gbit

  $0 stop <interface>
      停止故障注入,恢复接口正常带宽
      示例: $0 stop hccs0

  $0 status <interface>
      查看接口当前 tc 配置

参数:
  interface       网络接口名 (例如 hccs0, eth0)
  bandwidth_limit tc 格式的带宽限制 (例如 5gbit, 10mbit, 500kbit)

注意:
  - 需要 root 权限
  - 使用 HTB (Hierarchical Token Bucket) qdisc
  - 限流仅影响出向流量 (egress)
EOF
    exit 1
}

# 检查 root 权限
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: 需要 root 权限. 使用: sudo $0 $*"
    exit 1
fi

# 检查 tc 命令
if ! command -v tc &>/dev/null; then
    echo "ERROR: tc 命令未找到. 安装 iproute2: yum install iproute 或 apt install iproute2"
    exit 1
fi

# ---------------------------------------------------------------------------
# start: 启动故障注入
# ---------------------------------------------------------------------------
start_fault() {
    local iface="$1"
    local bw_limit="$2"

    echo "======================================================================"
    echo "  故障注入: 启动"
    echo "  接口:     $iface"
    echo "  限流带宽: $bw_limit"
    echo "  时间:     $(date)"
    echo "======================================================================"

    # 检查接口是否存在
    if ! ip link show "$iface" &>/dev/null; then
        echo "ERROR: 接口 $iface 不存在. 可用接口:"
        ip link show | grep -E '^[0-9]+:' | awk '{print $2}' | sed 's/:$//'
        exit 1
    fi

    # 删除现有 qdisc (如果有)
    echo "[1/3] 删除现有 qdisc (如果存在)..."
    tc qdisc del dev "$iface" root 2>/dev/null || true
    echo "  OK"

    # 添加 HTB qdisc
    echo "[2/3] 添加 HTB qdisc..."
    tc qdisc add dev "$iface" root handle 1: htb default 11
    echo "  OK"

    # 添加 HTB class 限流
    echo "[3/3] 添加限流规则 (rate=$bw_limit)..."
    tc class add dev "$iface" parent 1: classid 1:11 htb rate "$bw_limit"
    echo "  OK"

    # 显示配置
    echo ""
    echo "故障注入已启动. 当前配置:"
    tc qdisc show dev "$iface"
    tc class show dev "$iface"

    echo ""
    echo "======================================================================" 
    echo "  故障注入成功"
    echo "  接口 $iface 出向带宽已限制为 $bw_limit"
    echo "  停止: sudo $0 stop $iface"
    echo "======================================================================"
}

# ---------------------------------------------------------------------------
# stop: 停止故障注入
# ---------------------------------------------------------------------------
stop_fault() {
    local iface="$1"

    echo "======================================================================"
    echo "  故障注入: 停止"
    echo "  接口:     $iface"
    echo "  时间:     $(date)"
    echo "======================================================================"

    if ! ip link show "$iface" &>/dev/null; then
        echo "ERROR: 接口 $iface 不存在"
        exit 1
    fi

    # 删除 qdisc (恢复默认)
    echo "[1/1] 删除 tc qdisc,恢复正常带宽..."
    tc qdisc del dev "$iface" root 2>/dev/null || echo "  (无需删除,接口未配置 tc)"
    echo "  OK"

    echo ""
    echo "======================================================================"
    echo "  故障注入已停止"
    echo "  接口 $iface 已恢复正常带宽"
    echo "======================================================================"
}

# ---------------------------------------------------------------------------
# status: 查看状态
# ---------------------------------------------------------------------------
status_fault() {
    local iface="$1"

    echo "======================================================================"
    echo "  接口 $iface 的 tc 配置"
    echo "======================================================================"

    if ! ip link show "$iface" &>/dev/null; then
        echo "ERROR: 接口 $iface 不存在"
        exit 1
    fi

    echo ""
    echo "--- qdisc ---"
    tc qdisc show dev "$iface"
    echo ""
    echo "--- class ---"
    tc class show dev "$iface" 2>/dev/null || echo "(无 class 配置)"
    echo ""
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
case "$ACTION" in
    start)
        if [[ -z "$INTERFACE" || -z "$BANDWIDTH_LIMIT" ]]; then
            usage
        fi
        start_fault "$INTERFACE" "$BANDWIDTH_LIMIT"
        ;;
    stop)
        if [[ -z "$INTERFACE" ]]; then
            usage
        fi
        stop_fault "$INTERFACE"
        ;;
    status)
        if [[ -z "$INTERFACE" ]]; then
            usage
        fi
        status_fault "$INTERFACE"
        ;;
    *)
        usage
        ;;
esac
