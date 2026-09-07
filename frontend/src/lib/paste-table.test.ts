import { describe, expect, it } from "vitest";

import {
  mapPastedTable,
  parsePastedTable,
  parseTimepointHeader,
} from "@/lib/paste-table";

/**
 * The paste path is the single highest-value feature of P21b -- it is the
 * difference between typing forty cells and pasting them -- and it is also
 * the one that can quietly file 12-month data as 0-month data. So it is
 * tested here, without a browser or a component, at the level where the
 * mistakes actually live.
 */

const TESTS = [
  { id: "t1", test_name: "Assay" },
  { id: "t2", test_name: "Related substances - total" },
  { id: "t3", test_name: "Dissolution" },
];

describe("parsePastedTable", () => {
  it("reads the tab-separated text every spreadsheet puts on the clipboard", () => {
    expect(parsePastedTable("Test\t0\t6\nAssay\t99.4\t99.0")).toEqual([
      ["Test", "0", "6"],
      ["Assay", "99.4", "99.0"],
    ]);
  });

  it("survives Windows line endings", () => {
    // Without the \r being swallowed, "99.0\r" matches no number and the
    // last column of every row is silently lost.
    expect(parsePastedTable("Test\t0\r\nAssay\t99.4\r\n")).toEqual([
      ["Test", "0"],
      ["Assay", "99.4"],
    ]);
  });

  it("drops the phantom row a trailing newline leaves", () => {
    expect(parsePastedTable("Test\t0\nAssay\t99.4\n")).toHaveLength(2);
  });

  it("keeps a quoted cell that contains a newline in one cell", () => {
    const table = parsePastedTable('Test\t0\nAssay\t"99.4 %\n(mean of 3)"');
    expect(table).toHaveLength(2);
    expect(table[1][1]).toBe("99.4 %\n(mean of 3)");
  });

  it("reads a doubled quote inside a quoted cell as one quote", () => {
    expect(parsePastedTable('A\t"say ""hi"""')[0][1]).toBe('say "hi"');
  });
});

describe("parseTimepointHeader", () => {
  it.each([
    ["0", 0],
    ["6", 6],
    ["12 months", 12],
    ["18M", 18],
    ["T24", 24],
    ["3 mo", 3],
  ])("reads %s as %i months", (cell, months) => {
    expect(parseTimepointHeader(cell)).toBe(months);
  });

  it.each(["Test", "", "Batch 2", "Acceptance criterion"])(
    "refuses to guess a timepoint from %s",
    (cell) => {
      // Returning null rather than guessing is the same discipline the
      // acceptance parser follows: a wrong guess here files one
      // timepoint's data under another's.
      expect(parseTimepointHeader(cell)).toBeNull();
    },
  );
});

describe("mapPastedTable", () => {
  const PASTE = [
    "Test\t0\t6\t12",
    "Assay\t99.4 %\t99.0 %\t98.4 %",
    "Dissolution\t94 %\t93 %\t91 %",
  ].join("\n");

  it("maps a stability table onto the specification's own tests", () => {
    const mapping = mapPastedTable(parsePastedTable(PASTE), TESTS);

    expect(mapping.timepoints).toEqual([0, 6, 12]);
    expect(mapping.cells).toHaveLength(6);
    expect(mapping.cells[0]).toEqual({
      testId: "t1",
      timepointMonths: 0,
      value: "99.4 %",
    });
  });

  it("tolerates case and spacing in a test name but not a near-miss", () => {
    const table = parsePastedTable(
      "Test\t0\nRELATED  SUBSTANCES - TOTAL\t0.4 %\nAssayy\t99.4 %",
    );
    const mapping = mapPastedTable(table, TESTS);

    expect(mapping.cells).toEqual([
      { testId: "t2", timepointMonths: 0, value: "0.4 %" },
    ]);
    // A near-miss is REPORTED, never guessed at: guessing which test a
    // value answers is guessing which limit it will be judged against.
    expect(mapping.unmatchedRows).toEqual(["Assayy"]);
  });

  it("reports a column whose header names no timepoint", () => {
    const table = parsePastedTable("Test\t0\tRemarks\nAssay\t99.4 %\tOK");
    const mapping = mapPastedTable(table, TESTS);

    expect(mapping.unmatchedColumns).toEqual(["Remarks"]);
    expect(mapping.cells).toHaveLength(1);
  });

  it("skips an empty cell rather than recording an empty result", () => {
    // A blank in a stability table means "not tested at this timepoint",
    // which the rendered section states in words. An empty string stored
    // as a result would be a different, and worse, claim.
    const table = parsePastedTable("Test\t0\t6\nAssay\t99.4 %\t");
    const mapping = mapPastedTable(table, TESTS);

    expect(mapping.cells).toHaveLength(1);
  });
});
