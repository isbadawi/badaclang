import pycparser


def ast(filename):
    return pycparser.parse_file(filename, use_cpp=True)
