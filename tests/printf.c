extern int printf(const char *, ...);

int main(int argc, char *argv[]) {
  int x;
  x = argc;
  printf("hello, %s (got %d arguments)\n", "world", x - 1);
  if (x > 1) {
    printf("first argument is %s\n", argv[1]);
  } else {
    printf("no arguments!\n");
  }
  return 0;
}
