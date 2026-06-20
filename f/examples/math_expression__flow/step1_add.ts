export async function main(a: number, b: number): Promise<number> {
  const sum = a + b;
  console.log(`Step 1: ${a} + ${b} = ${sum}`);
  return sum;
}
