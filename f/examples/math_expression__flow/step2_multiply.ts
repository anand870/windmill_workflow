export async function main(sum: number, a: number): Promise<number> {
  const product = sum * a;
  console.log(`Step 2: ${sum} * ${a} = ${product}`);
  return product;
}
