// RUN: badaclang %s -o %t.ll
// RUN: clang %t.ll -o %t
// RUN: echo 37 | %t | grep 'Yes! You got it in 1 guesses.'
extern int scanf(const char*, ...);
extern int printf(const char*, ...);

#define MAXGUESSES 10

int main(int argc, char *argv[]) {
  printf("Guess a number between 1 and 100!\n");
  int i;
  int target = 37;

  int guesses[MAXGUESSES];

  int guess = -1;
  int nguesses = 0;
  while (guess != target && nguesses < MAXGUESSES) {
    scanf("%d", &guess);
    guesses[nguesses++] = guess;
    if (guess < target) {
      printf("Higher!\n");
    } else if (guess > target) {
      printf("Lower!\n");
    } else {
      printf("Yes! You got it in %d guesses.\n", nguesses);
      printf("Your guesses were: ");
      for (i = 0; i < nguesses; i++) {
        printf("%d ", guesses[i]);
      }
      printf("\n");
    }
  }

  if (nguesses == MAXGUESSES) {
    printf("You used up all your guesses. The answer was %d.\n", target);
  }
  return 0;
}
