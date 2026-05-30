export function env(name, fallback = undefined) {
  const value = process.env[name] ?? fallback;
  if (value === undefined || value === "") {
    throw new Error(`Missing required env var: ${name}`);
  }
  return value;
}

export function optionalEnv(name, fallback = "") {
  return process.env[name] ?? fallback;
}

export function csvEnv(name, fallback = "") {
  return optionalEnv(name, fallback)
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}
