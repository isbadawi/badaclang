extern int printf(const char *, ...);

int main(int argc, char *argv[]) {
  int x = argc;
  printf("hello, %s (got %d arguments)\n", "world", argc + x - x);
  return 0;
}
