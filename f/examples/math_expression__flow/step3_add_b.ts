export async function main(product: number, b: number): Promise<number> {
  const result = product + b;
  console.log(`Step 3: ${product} + ${b} = ${result}`);
  return result;
}
