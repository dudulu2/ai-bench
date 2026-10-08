"""故障注入点登记。混沌测试靠本文件验证并发/事务的原子性。

契约的一部分：不得删除已登记的注入点；可以新增，但必须同时在这里登记。
"""

POINTS = {
    "report_work": "共用工序并发报工",
    "review_count": "多人同时复核同一张盘点单",
    "approve_segment": "并行会签段同时点击",
    "issue_material": "领料与台账扣减的原子性",
    "settle_count": "审定与对账的原子性",
}

ENABLED = set(POINTS)


def before_write(point, conn=None):
    """写入前的注入钩子。默认直通；混沌测试会替换它来制造延迟/中断。"""
    if point not in ENABLED:
        raise KeyError(f"未登记的注入点: {point}")
    hook = _HOOK.get(point)
    if hook:
        hook(conn)
    return True


_HOOK = {}


def install(point, fn):
    if point not in POINTS:
        raise KeyError(f"未登记的注入点: {point}")
    _HOOK[point] = fn


def uninstall(point):
    _HOOK.pop(point, None)


def register(name, desc):
    """新增注入点时必须调用，否则混沌测试无法感知。"""
    POINTS[name] = desc
    ENABLED.add(name)
