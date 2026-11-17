export type Operation = "add" | "subtract" | "multiply" | "divide";

export type CalculateArgs = {
  a: number;
  b: number;
  operation: Operation;
};

/** The tool implementation: plain TypeScript, deterministic and independent of the model. */
export function calculate({ a, b, operation }: CalculateArgs): number {
  if (!Number.isFinite(a) || !Number.isFinite(b)) {
    throw new Error("a 和 b 必须是有限数字");
  }

  let result: number;
  switch (operation) {
    case "add": result = a + b; break;
    case "subtract": result = a - b; break;
    case "multiply": result = a * b; break;
    case "divide":
      if (b === 0) throw new Error("除数不能为 0");
      result = a / b;
      break;
    default: throw new Error("不支持的运算");
  }

  if (!Number.isFinite(result)) throw new Error("计算结果超出范围");
  return result;
}
