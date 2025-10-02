# Bikeshed Rust Extensions

This directory contains Rust implementations of Bikeshed modules, compiled to Python extensions using PyO3.

## Building

```bash
# Install maturin (build tool)
cargo install maturin

# Build release wheel
cd rust
maturin build --release
```

## Testing

## Using Rust Extensions

```bash
# Use Rust implementation
export BIKESHED_USE_RUST=1
bikeshed spec input.bs output.html

# Use Python implementation (default)
export BIKESHED_USE_RUST=0
bikeshed spec input.bs output.html
```
