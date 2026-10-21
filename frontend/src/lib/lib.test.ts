import { describe, expect, it } from "vitest";
import { pctChange, zl } from "@/operator/lib";
import { DEFAULT_BOARD, polarToXY, scoreAt } from "./board";
import { dartLabel, gameMessage, plural } from "./pl";

describe("scoreAt (client-side board geometry, must match the backend)", () => {
  const at = (r: number, deg: number) => scoreAt(DEFAULT_BOARD, ...polarToXY(r, deg)).label;

  it("scores bulls and misses by radius", () => {
    expect(at(0, 0)).toBe("BULL");
    expect(at(10, 0)).toBe("25");
    expect(at(171, 0)).toBe("MISS");
  });

  it("scores rings of the 20 (straight up)", () => {
    expect(at(60, 0)).toBe("S20");
    expect(at(103, 0)).toBe("T20");
    expect(at(166, 0)).toBe("D20");
  });

  it("goes clockwise from the 20", () => {
    expect(at(60, 18)).toBe("S1");
    expect(at(60, 90)).toBe("S6");
    expect(at(60, 180)).toBe("S3");
    expect(at(60, 270)).toBe("S11");
    expect(at(60, 351)).toBe("S20"); // within half a sector of the 20
    expect(at(60, 342)).toBe("S5");
  });
});

describe("Polish labels", () => {
  it("shows singles as the bare number", () => {
    expect(dartLabel("S20")).toBe("20");
    expect(dartLabel("T20")).toBe("T20");
    expect(dartLabel("MISS")).toBe("Pudło");
  });

  it("uses Polish plural forms", () => {
    expect(plural(1, "runda", "rundy", "rund")).toBe("runda");
    expect(plural(3, "runda", "rundy", "rund")).toBe("rundy");
    expect(plural(5, "runda", "rundy", "rund")).toBe("rund");
    expect(plural(12, "runda", "rundy", "rund")).toBe("rund");
    expect(plural(22, "runda", "rundy", "rund")).toBe("rundy");
  });

  it("translates game messages", () => {
    expect(gameMessage("Ala wins leg 2")).toBe("Ala wygrywa lega 2");
    expect(gameMessage("Ala wins the game")).toBe("Ala wygrywa mecz");
    expect(gameMessage("BUST")).toBe("BUST — za dużo");
  });
});

describe("operator formatting", () => {
  it("formats money in złoty (Polish grouping starts at 5 digits)", () => {
    expect(zl(1234).replace(/\s/g, " ")).toBe("1234 zł");
    expect(zl(73434).replace(/\s/g, " ")).toBe("73 434 zł");
  });

  it("computes percentage change, none without a previous period", () => {
    expect(pctChange(150, 100)).toBeCloseTo(50);
    expect(pctChange(10, 0)).toBeNull();
  });
});
