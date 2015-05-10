extern int printf(const char *, ...);

int main(int argc, char *argv[]) {
  int x = argc;
  printf("hello, %s (got %d arguments)\n", "world", argc + x - x);
  if (argc > 1) {
    printf("first argument is %s\n", argv[1]);
  } else {
    printf("no arguments!\n");
  }
  return 0;
}
