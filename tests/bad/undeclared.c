// RUN: ! badaclang %s 2> %t
// RUN: grep < %t "use of undeclared identifier 'puts'"
int main(void) {
  puts("hello, world");
  return 0;
}
