// RUN: badaclang %s -o %t.ll
// RUN: clang %t.ll -o %t
// RUN: %t | grep 'hello, world'
extern int puts(const char *);

int main(int argc, char *argv[]) {
  puts("hello, world");
  return 0;
}
