# Observed guest functions

`symbols.csv` records verified addresses and the evidence for each entry.
`CONFIRMED` describes the observed address/body/call relationship; it does not
assign an unverified engine purpose. Unknown routines retain `FUN_` names.

`hot_functions.csv` catalogs eight recurring routines and their direct-call
neighborhood. Instruction-comment and vector-comment counts describe the
generated guest instructions, not retired native instructions or runtime call
frequency. Empty caller fields mean no direct caller was found by this tool;
indirect dispatch is outside that search.

Regenerate metadata into a new file for review:

```powershell
python tools/catalog_hot_functions.py port/generated/default 84723778 84723CC0 84724930 84725580 847262B8 84726920 847269E0 84DCB0C8 --output work/hot-functions-new.csv
```

Measured sample/call counts, normalized costs, correctness checks and scope are
in the [hot-function finding](../findings/2026-11-01-hot-functions-and-vector-pack.md).
Raw native profiles and generated game code remain ignored and local.
