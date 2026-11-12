export function shippingCost(total, region = "domestic") {
  if (!Number.isFinite(total) || total < 0) {
    throw new Error("Total must be a nonnegative finite number.");
  }
  if (region === "international") {
    return total >= 200 ? 10 : 25;
  }
  if (region !== "domestic") {
    throw new Error("Unsupported region.");
  }
  return total >= 50 ? 0 : 5;
}

export function loyaltyDiscount(points) {
  if (points >= 1000) {
    return 0.15;
  }
  if (points >= 500) {
    return 0.05;
  }
  return 0;
}
