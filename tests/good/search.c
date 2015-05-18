// RUN: badaclang %s -o %t.ll
// RUN: clang %t.ll -o %t
// RUN: %t | grep 'All good!'

extern int puts(const char*);

int linear_search(int target, int* x, int len) {
  int i = 0;
  int result = -1;
  for (i = 0; i < len; ++i) {
    if (x[i] == target) {
      result = i;
      break;
    }
  }
  return result;
}

int main(void) {
  int x[10] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9};
  int found = linear_search(6, x, 10);
  int notfound = linear_search(16, x, 10);

  if (found != 6 || notfound != -1) {
    return 1;
  }

  puts("All good!");
  return 0;
}
