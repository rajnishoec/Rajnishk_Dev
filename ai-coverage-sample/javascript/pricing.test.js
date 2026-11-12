import assert from "node:assert/strict";
import test from "node:test";
import { shippingCost } from "./pricing.js";

test("large domestic orders ship free", () => {
  assert.equal(shippingCost(100), 0);
});

test("small domestic orders pay shipping", () => {
  assert.equal(shippingCost(20), 5);
});
