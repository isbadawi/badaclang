# badaclang

badaclang is a C to LLVM compiler written in python. It uses [pycparser][] to
parse C code, and [llvmlite][] to generate LLVM IR.

### Usage

Given a C file, it outputs LLVM IR on stdout. You can then use clang to make an
executable out of it:

```bash
$ python badaclang.py hello.c > hello.ll
$ clang hello.ll -o hello
$ ./hello
hello, world!
```

[pycparser]: https://github.com/eliben/pycparser
[llvmlite]: https://github.com/numba/llvmlite
