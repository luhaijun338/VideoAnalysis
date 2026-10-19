import { describe, expect, it } from "vitest";
import { formatClock, formatOperationLogLine } from "./operationLog";

describe("formatClock", () => {
  it("formats mm:ss from ms", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(65000)).toBe("1:05");
  });
});

describe("formatOperationLogLine", () => {
  it("prefers caption over OCR", () => {
    expect(formatOperationLogLine(12000, "在「网元」· 修改网元 · IP", "噪声")).toBe(
      "[0:12] 在「网元」· 修改网元 · IP",
    );
  });

  it("falls back to compacted OCR", () => {
    expect(formatOperationLogLine(5000, "", "导出\n客户")).toBe("[0:05] 导出 客户");
  });

  it("uses placeholder when empty", () => {
    expect(formatOperationLogLine(0, "  ", "")).toBe("[0:00] （无描述）");
  });
});
