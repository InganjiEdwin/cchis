export const PASSWORD_MIN_LENGTH = 12;
export const GENERATED_PASSWORD_LENGTH = 18;

const LOWERCASE_CHARACTERS = "abcdefghjkmnpqrstuvwxyz";
const UPPERCASE_CHARACTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ";
const NUMBER_CHARACTERS = "23456789";
const SYMBOL_CHARACTERS = "!@#$%^&*()-_=+[]{}?";
const ALL_GENERATOR_CHARACTERS =
  LOWERCASE_CHARACTERS + UPPERCASE_CHARACTERS + NUMBER_CHARACTERS + SYMBOL_CHARACTERS;

export type PasswordPolicyRequirement = {
  id: "length" | "lowercase" | "uppercase" | "number" | "symbol";
  label: string;
  isMet: boolean;
};

export function getPasswordPolicyRequirements(password: string): PasswordPolicyRequirement[] {
  return [
    {
      id: "length",
      label: `At least ${PASSWORD_MIN_LENGTH} characters`,
      isMet: password.length >= PASSWORD_MIN_LENGTH,
    },
    {
      id: "lowercase",
      label: "Lowercase letter",
      isMet: /[a-z]/.test(password),
    },
    {
      id: "uppercase",
      label: "Uppercase letter",
      isMet: /[A-Z]/.test(password),
    },
    {
      id: "number",
      label: "Number",
      isMet: /\d/.test(password),
    },
    {
      id: "symbol",
      label: "Symbol",
      isMet: /[^A-Za-z0-9]/.test(password),
    },
  ];
}

export function getPasswordPolicyError(password: string) {
  const unmet = getPasswordPolicyRequirements(password).filter((requirement) => !requirement.isMet);

  if (unmet.length === 0) {
    return null;
  }

  return `Use at least ${PASSWORD_MIN_LENGTH} characters with uppercase, lowercase, a number, and a symbol.`;
}

export function isStrongPassword(password: string) {
  return getPasswordPolicyError(password) === null;
}

function getSecureRandomInt(maxExclusive: number) {
  const crypto = globalThis.crypto;

  if (!crypto?.getRandomValues) {
    throw new Error("Secure password generation is unavailable in this browser.");
  }

  const randomValues = new Uint32Array(1);
  const maximumUnbiasedValue = Math.floor(0x100000000 / maxExclusive) * maxExclusive;

  do {
    crypto.getRandomValues(randomValues);
  } while (randomValues[0]! >= maximumUnbiasedValue);

  return randomValues[0]! % maxExclusive;
}

function getRandomCharacter(characters: string) {
  return characters[getSecureRandomInt(characters.length)]!;
}

export function generateStrongPassword(length = GENERATED_PASSWORD_LENGTH) {
  const passwordLength = Math.max(length, PASSWORD_MIN_LENGTH, 4);
  const characters = [
    getRandomCharacter(LOWERCASE_CHARACTERS),
    getRandomCharacter(UPPERCASE_CHARACTERS),
    getRandomCharacter(NUMBER_CHARACTERS),
    getRandomCharacter(SYMBOL_CHARACTERS),
  ];

  while (characters.length < passwordLength) {
    characters.push(getRandomCharacter(ALL_GENERATOR_CHARACTERS));
  }

  for (let index = characters.length - 1; index > 0; index -= 1) {
    const swapIndex = getSecureRandomInt(index + 1);
    [characters[index], characters[swapIndex]] = [characters[swapIndex]!, characters[index]!];
  }

  return characters.join("");
}
