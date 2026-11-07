import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_inline_switches import classify, read_emitted


def test_parse_unscaled_selector_and_signed_low_table_address():
    source = """DEFINE_REX_FUNC(sub_84000000) {
    // lis r12,-31744
    ctx.r12.s64 = 0;
    // addi r12,r12,-16
    ctx.r12.s64 += -16;
    // rlwinm r0,r7,2,0,29
    ctx.r0.u64 = 0;
    // lwzx r0,r12,r0
    ctx.r0.u64 = 0;
    // mtctr r0
    ctx.ctr.u64 = ctx.r0.u64;
    // bctr
    switch (ctx.r7.u32) {
    case 0:
        goto loc_84000040;
\t}
}
"""
    result = read_emitted(source)
    assert result == {0x83FFFFF0: {"register": 7, "labels": [0x84000040], "function": "sub_84000000"}}
    assert read_emitted(source.replace("switch (ctx.r7", "switch (ctx.r8"))[0x83FFFFF0]["register"] == 8


@pytest.mark.parametrize("register,labels,truncated,disagreements", [
    (7, [0x84000040], 1, 0),
    (7, [0x84000040, 0x84000050], 0, 0),
    (7, [0x84000060], 0, 1),
    (8, [0x84000040], 0, 1),
])
def test_only_identical_prefixes_are_eligible(register, labels, truncated, disagreements):
    tables = [{"address": 0x8400002C, "register": 7, "labels": [0x84000040, 0x84000050]}]
    emitted = {0x84000030: {"register": register, "labels": labels, "function": "sub_84000000"}}
    recovered, rejected = classify(tables, emitted)
    assert len(recovered) == truncated
    assert len(rejected) == disagreements
