import { describe, expect, it } from "vitest";
import { seekSeconds } from "./seek";

describe("seekSeconds", () => {
  it("subtracts one second", () => {
    expect(seekSeconds(123000)).toBe(122);
  });
  it("floors at zero", () => {
    expect(seekSeconds(400)).toBe(0);
  });
});
