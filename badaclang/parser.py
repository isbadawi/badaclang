import pycparser


def ast(filename):
    # n.b. pycparser doesn't handle comments, expecting them to have been
    # removed by the preprocessor. It looks like clang's preprocessor doesn't
    # remove comments by default (?), but does when passed -xc++.
    return pycparser.parse_file(filename, use_cpp=True, cpp_args='-xc++')
