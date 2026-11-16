# Synthetic CHMOD example

`synthetic-art.chmod` contains a user-authored BC1 DDS replacement and a complete
API 1 manifest. It targets the synthetic Xbox TXTR bank used by the automated
tests, **not a retail game resource**. It installs through Mods but deliberately
fails retail revision validation on enable. Its synthetic IDs must not be
copied into a real mod. No game files or licensed artwork are included.

For a real package, Studio/exporters must read the actual Xbox installation's
bank/record identities and original DDS SHA256, supply authored DDS bytes, and
pin the supported retail XEX. See [current CHMOD specification](../docs/formats/chmod-1.2.md).
Do not claim the example is an in-game verified cosmetic mod.

Developers can reproduce the package with the checkout's Python test environment:
`port/out/python-env/Scripts/python.exe examples/make_chmod_example.py`.
Normal installation and loading require only the existing Windows launcher and
its distributed native tools. The generator and tests are not player dependencies.


The [native hook example](native-weight/README.md) includes instructions to build
`native-weight-example.chmod` from source. It was compiled,
not loaded or tested, and requires explicit unsandboxed-code opt-in.


API1.3 neutral C++ examples: `native-observe-example.chmod`,
`native-transform-example.chmod`, and `native-replace-example.chmod`.
They contain compiled user-authored DLLs demonstrating observation, identity
setter-argument transformation and original-delegating replacement. They were
compiled/packaged, never installed, enabled or executed. They require native-code
opt-in and the new runtime receipt. No gameplay tuning or existing patch is
implemented. Source/build/package instructions are in [the SDK](../sdk/README.md).

Generate example packages locally using the linked build and packaging instructions.
