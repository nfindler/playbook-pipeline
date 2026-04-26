// CLI-tests v31 Wave 3b: sample sanity test. Asserts the runner works.
test("sanity: 1 + 1 === 2", () => { expect(1 + 1).toBe(2); });
test("sanity: env loads", () => { expect(process.env.PATH).toBeTruthy(); });
