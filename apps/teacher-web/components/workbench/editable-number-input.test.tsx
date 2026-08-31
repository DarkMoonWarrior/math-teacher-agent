import { describe, expect, it } from "vitest";
import { parseEditableNumber } from "./editable-number-input";

describe("parseEditableNumber", () => {
  it("keeps an emptied number input uncommitted until the teacher types a replacement", () => {
    expect(parseEditableNumber("")).toBeNull();
    expect(parseEditableNumber("1")).toBe(1);
  });

  it("supports decimal scores without committing incomplete input", () => {
    expect(parseEditableNumber("-")).toBeNull();
    expect(parseEditableNumber("5.5")).toBe(5.5);
  });
});
