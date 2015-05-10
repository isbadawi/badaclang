extern int scanf(const char*, ...);
extern int printf(const char*, ...);

int main(int argc, char *argv[]) {
  printf("Guess a number between 1 and 100!\n");
  int target = 37;

  int guess = -1;
  int guesses = 0;
  while (guess != target) {
    scanf("%d", &guess);
    guesses = guesses + 1;
    if (guess < target) {
      printf("Higher!\n");
    } else if (guess > target) {
      printf("Lower!\n");
    } else {
      printf("Yes! You got it in %d guesses.\n", guesses);
    }
  }
  return 0;
}
