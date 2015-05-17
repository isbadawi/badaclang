// RUN: ! badaclang %s 2> %t
// RUN: grep < %t "redefinition of 'main'"
int main(void) {
  return 0;
}

int main(void) {
  return 0;
}
