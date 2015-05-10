extern int printf(const char *, ...);

int main(int argc, char *argv[]) {
  printf("hello, %s (%d)\n", "world", 2 + 3);
  return 0;
}
