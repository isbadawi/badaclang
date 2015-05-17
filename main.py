import argparse
import os
import sys

import badaclang


def parse_args():
    parser = argparse.ArgumentParser(description='badaclang')
    parser.add_argument('file', type=str, help='File to compile')
    parser.add_argument('-o', metavar='file', type=str, required=False,
                        dest='output', help='write output to file')
    args = parser.parse_args()
    if args.output is None:
        base, ext = os.path.splitext(args.file)
        args.output = '%s.ll' % base
    return args


def main():
    args = parse_args()
    ast = badaclang.parser.ast(args.file)

    try:
        scopes = badaclang.symbol.table(ast)
    except badaclang.symbol.SymbolError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    module = badaclang.codegen.llvm_module(args.file, ast, scopes)

    with open(args.output, 'w') as f:
        f.write(str(module))

if __name__ == '__main__':
    main()
