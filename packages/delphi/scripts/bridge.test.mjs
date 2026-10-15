import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  classifyError,
  createFetchGate,
  fixedMessage,
  handle,
  holdsSecret,
} from "./bridge.mjs";

test("a failure sentence is fixed and does not echo upstream text", () => {
  const marker = "UPSTREAM-MARKER-SENTENCE";
  const text = fixedMessage("upstream", "500");
  assert.equal(text.includes(marker), false);
  assert.equal(text, "The upstream read failed. (500)");
});

test("one decode keeps a 12 character window of the secret", () => {
  const secret = "SyntheticKey0123456789ABCDEF";
  const percent = [...secret].map((ch) => `%${ch.charCodeAt(0).toString(16).padStart(2, "0")}`).join("");
  const unicode = [...secret].map((ch) => `\\u${ch.charCodeAt(0).toString(16).padStart(4, "0")}`).join("");
  const literal = "\\u0041\\u0042\\u0043\\u0044";
  const wrapped = [...literal].map((ch) => `%${ch.charCodeAt(0).toString(16).padStart(2, "0")}`).join("");
  assert.equal(holdsSecret(secret, secret), true);
  assert.equal(holdsSecret(percent, secret), true);
  assert.equal(holdsSecret(unicode, secret), true);
  const both = [...percent].map((ch) => `\\u${ch.charCodeAt(0).toString(16).padStart(4, "0")}`).join("");
  assert.equal(holdsSecret(both, secret), true);
  assert.equal(holdsSecret(wrapped, literal), true);
  assert.equal(holdsSecret(secret.slice(0, 12), secret), true);
});

test("status comes from a typed field or the SDK prefix, not from argument text", () => {
  for (const message of [
    "API request failed (429)",
    "Health check failed (429)",
    "Subgraph request failed (429)",
  ]) {
    assert.equal(classifyError(new Error(message), "list_markets"), "rate_limited");
  }
  const http = new Error("HTTP request failed.");
  http.status = 429;
  http.name = "HttpRequestError";
  assert.equal(classifyError(http, "quote_buy"), "rate_limited");
  assert.equal(classifyError(new Error("API request failed (401)"), "list_markets"), "auth");
  assert.equal(classifyError(new Error("API request failed (401)"), "quote_buy"), "upstream");
  assert.equal(classifyError(new Error("API request failed (404)"), "get_market"), "not_found");
  assert.equal(classifyError(new Error("Subgraph request failed (404)"), "subgraph_trades"), "unsupported_market");
  assert.equal(fixedMessage("not_found", "404"), "The market is not in the API list. (404)");
  const rpc = new Error("Request is being rate limited");
  rpc.code = 429;
  rpc.name = "RpcRequestError";
  assert.equal(classifyError(rpc, "live_edge"), "rate_limited");
  assert.equal(classifyError(new Error("socket closed")), "upstream");
  const echoed = new Error("execution reverted: outcome 401 shares 0.000000000000000429");
  assert.equal(classifyError(echoed, "quote_buy"), "upstream");
  echoed.name = "ContractFunctionRevertedError";
  assert.equal(classifyError(echoed, "quote_buy"), "market_not_quotable");
});

test("retries still stop at the reserved budget", async () => {
  let sent = 0;
  const fake = async () => {
    sent += 1;
    return { status: 500 };
  };
  const gate = createFetchGate(fake, 2);
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      await gate.fetch("https://example.invalid");
    } catch (error) {
      assert.match(String(error), /budget/);
    }
  }
  assert.equal(sent, 2);
  assert.equal(gate.count(), 2);
});

test("a secret that is itself an escape is visible in the original text", () => {
  for (const secret of ["aaaaaaa%41bbbbbbb", "abcdefg%41hijklmn%42opqrstu", "ab\\u0041cd"]) {
    assert.equal(holdsSecret(secret, secret), true);
    assert.equal(fixedMessage("upstream").includes(secret), false);
  }
});

test("a revert does not return the contract call", () => {
  const error = new Error("execution reverted: 0x22ea355D7218Dc86b4c83732cBbd01f7Ff2332b3 quote(1)");
  error.name = "ContractFunctionRevertedError";
  const text = fixedMessage(classifyError(error, "quote_buy"));
  assert.equal(classifyError(error, "quote_buy"), "market_not_quotable");
  assert.equal(text, "The market could not be quoted.");
  assert.equal(text.includes("0x22ea"), false);
});

test("fetch budget refuses before another request is sent", async () => {
  let sent = 0;
  const fake = async () => {
    sent += 1;
    return { status: 200 };
  };
  const zero = createFetchGate(fake, 0);
  await assert.rejects(zero.fetch("https://example.invalid"));
  assert.equal(sent, 0);
  const one = createFetchGate(fake, 1);
  await one.fetch("https://example.invalid");
  await assert.rejects(one.fetch("https://example.invalid"));
  assert.equal(sent, 1);
  assert.equal(one.count(), 1);
});

test("fetch gate blocks other hosts, redirects, and leaked key headers", async () => {
  const seen = [];
  const fake = async (url, init) => {
    seen.push({ url: String(url), redirect: init.redirect, key: new Headers(init.headers).get("x-api-key") });
    return { status: init.status ?? 200 };
  };
  const gate = createFetchGate(fake, 3, new Set(["delphi-api.gensyn.ai", "api.goldsky.com"]));
  await assert.rejects(gate.fetch("http://delphi-api.gensyn.ai/markets", {
    headers: { "X-API-Key": "marker" },
  }));
  assert.equal(seen.length, 0);
  await assert.rejects(gate.fetch("https://evil.example/markets", {
    headers: { "X-API-Key": "marker" },
  }));
  assert.equal(seen.length, 0);
  await gate.fetch("https://api.goldsky.com/meta", { headers: { "X-API-Key": "marker" } });
  assert.equal(seen[0].key, null);
  assert.equal(seen[0].redirect, "manual");
  await assert.rejects(
    gate.fetch("https://delphi-api.gensyn.ai/markets", { status: 302, headers: { "X-API-Key": "marker" } }),
    /redirected/,
  );
  assert.equal(seen[1].key, "marker");
});

test("a disposable key never leaves the bridge", async () => {
  const disposable = `0x${"ab".repeat(32)}`;
  const page = await handle(
    {
      op: "quote_buy",
      network: "testnet",
      max_outbound: 4,
      args: { market_address: "0x" + "11".repeat(20), outcome_idx: 0, shares_raw: "1" },
    },
    async () => {
      throw new Error("fetch should not run");
    },
    () => ({
      disposable,
      client: {
        quoteBuy: async () => {
          const error = new Error(`reverted with signer ${disposable}`);
          error.name = "ContractFunctionRevertedError";
          throw error;
        },
      },
    }),
  );
  const text = JSON.stringify(page);
  assert.equal(page.ok, false);
  assert.equal(page.error_type, "market_not_quotable");
  assert.equal(text.includes(disposable), false);
  assert.equal(text.includes(disposable.slice(2)), false);
  assert.equal(text.includes(disposable.slice(2, 10)), false);
  const upper = disposable.toUpperCase();
  const split = upper.split("").join("\u200b");
  const encoded = upper.replace(/./g, (char) => `%${char.charCodeAt(0).toString(16)}`);
  const leaked = await handle(
    {
      op: "quote_sell",
      network: "testnet",
      max_outbound: 4,
      args: { market_address: "0x" + "11".repeat(20), outcome_idx: 0, shares_raw: "1" },
    },
    async () => {
      throw new Error("fetch should not run");
    },
    () => ({
      disposable,
      client: {
        quoteSell: async () => {
          throw new Error(`reverted ${upper} ${split} ${encoded}`);
        },
      },
    }),
  );
  const hidden = JSON.stringify(leaked).toLowerCase();
  assert.equal(leaked.ok, false);
  assert.equal(hidden.includes(disposable.slice(2)), false);
  assert.equal(hidden.includes(disposable.slice(2, 10)), false);
});

test("live edge carries exponent text", async () => {
  const page = await handle(
    {
      op: "live_edge",
      network: "testnet",
      max_outbound: 3,
      args: { market_id: "0x" + "11".repeat(20), outcome_idx: 0 },
    },
    async () => {
      throw new Error("fetch should not run");
    },
    () => ({
      disposable: `0x${"cd".repeat(32)}`,
      client: {
        getMarket: async () => ({
          id: "0x" + "11".repeat(20),
          metadata: { outcomes: ["a", "b", "c", "d"] },
          spotImpliedProbabilities: [1e-7, 5e-324, 0, 1],
        }),
      },
    }),
  );
  assert.equal(page.ok, true);
  assert.deepEqual(page.result.spotImpliedProbabilities, ["1e-7", "5e-324", "0", "1"]);
});

test("an lmsr market probability is unsupported", async () => {
  const page = await handle(
    {
      op: "live_edge",
      network: "testnet",
      max_outbound: 3,
      args: { market_id: "0x" + "11".repeat(20), outcome_idx: 0 },
    },
    async () => { throw new Error("fetch should not run"); },
    () => ({
      disposable: "",
      client: {
        getMarket: async () => ({
          id: "0x" + "11".repeat(20),
          metadata: { outcomes: ["a", "b"], mechanism_type: "lmsr" },
          spotImpliedProbabilities: [],
        }),
      },
    }),
  );
  assert.equal(page.ok, false);
  assert.equal(page.error_type, "unsupported_market");
  assert.equal(page.detail, "lmsr_probability");
  assert.equal(page.message, "This tool does not return a probability for an lmsr market.");
});

test("an empty price read is an upstream failure, not a broken shape", async () => {
  const page = await handle(
    {
      op: "live_edge",
      network: "testnet",
      max_outbound: 3,
      args: { market_id: "0x" + "11".repeat(20), outcome_idx: 0 },
    },
    async () => { throw new Error("fetch should not run"); },
    () => ({
      disposable: "",
      client: {
        getMarket: async () => ({
          id: "0x" + "11".repeat(20),
          metadata: { outcomes: ["a", "b"] },
          spotImpliedProbabilities: [],
        }),
      },
    }),
  );
  assert.equal(page.ok, false);
  assert.equal(page.error_type, "upstream");
  assert.equal(page.message, "The upstream read failed.");
});

test("live edge rejects a different market id", async () => {
  const page = await handle(
    {
      op: "live_edge",
      network: "testnet",
      max_outbound: 3,
      args: { market_id: `0x${"11".repeat(20)}`, outcome_idx: 0 },
    },
    async () => {
      throw new Error("fetch should not run");
    },
    () => ({
      disposable: `0x${"ab".repeat(32)}`,
      client: {
        getMarket: async () => ({
          id: `0x${"22".repeat(20)}`,
          metadata: { outcomes: ["yes", "no"] },
          spotImpliedProbabilities: [0.25, 0.75],
        }),
      },
    }),
  );
  assert.equal(page.ok, false);
  assert.equal(page.error_type, "invalid_response");
  assert.equal(Object.hasOwn(page, "result"), false);
});

test("quote decimals accept a bigint byte", async () => {
  const page = await handle(
    {
      op: "quote_buy",
      network: "testnet",
      max_outbound: 4,
      args: { market_address: `0x${"11".repeat(20)}`, outcome_idx: 0, shares_raw: "1" },
    },
    async () => {
      throw new Error("fetch should not run");
    },
    () => ({
      disposable: `0x${"ab".repeat(32)}`,
      client: {
        quoteBuy: async () => ({ tokensIn: 929216n }),
        getErc20BalanceWithDecimals: async () => ({ decimals: 6n, balance: 1n }),
      },
    }),
  );
  assert.equal(page.ok, true);
  assert.equal(page.result.decimals.status, "known");
  assert.equal(page.result.decimals.value, 6);
  assert.equal(page.result.amount_raw, "929216");
});

test("compute_edge is not a bridge operation", async () => {
  const reply = await handle(
    {
      op: "compute_edge",
      args: { implied_probability: "0.4", your_probability: "0.5" },
      network: "testnet",
      max_outbound: 0,
    },
    async () => {
      throw new Error("network disabled");
    },
  );
  assert.equal(reply.ok, false);
  assert.equal(reply.message, "The upstream read failed.");
  assert.equal(reply.message.includes("Unsupported"), false);
});

test("bridge executable reads one bounded request from stdin", () => {
  const bridge = fileURLToPath(new URL("./bridge.mjs", import.meta.url));
  const child = spawnSync(process.execPath, [bridge], {
    input: JSON.stringify({ op: "unknown", args: {}, max_outbound: 0, network: "testnet" }),
    encoding: "utf8",
    timeout: 5_000,
  });
  assert.equal(child.status, 0);
  const reply = JSON.parse(child.stdout);
  assert.equal(reply.ok, false);
  assert.equal(reply.message, "The upstream read failed.");
  assert.equal(reply.message.includes("Unsupported"), false);
  assert.doesNotMatch(reply.message, /path.*argument/);
});

test("a body without the page field is not an empty page", async () => {
  const gate = createFetchGate(async () => ({
    status: 200,
    ok: true,
    clone() { return { json: async () => ({ message: "no page" }) }; },
  }), 1);
  await gate.fetch("https://delphi-api.gensyn.ai/v1/markets");
  assert.deepEqual(gate.pages, [false]);
});

test("a legacy gateway is read from the older subgraph on the same host", async () => {
  const seen = [];
  const reply = await handle(
    {
      op: "subgraph_trades",
      args: { market_address: "0xf8022b5c02ab07ad52c3067a70578aa639483697", first: 1, skip: 0 },
      network: "testnet",
      max_outbound: 2,
    },
    async (input) => {
      seen.push(String(input));
      return {
        status: 200,
        ok: true,
        json: async () => ({ data: { gatewayBuys: [], gatewaySells: [] } }),
      };
    },
    () => ({
      disposable: "",
      client: {
        resolveGateway: async () => "0x7b8FDBD187B0Be5e30e48B1995df574A62667147",
        getSubgraphUrl: () => (
          "https://api.goldsky.com/api/public/project_x/subgraphs/delphi-testnet-autoset/1.0.0/gn"
        ),
        getSubgraph() { throw new Error("automated subgraph was used"); },
      },
    }),
  );
  assert.equal(seen.some((url) => url.includes("delphi-testnet-autoset")), false);
  assert.equal(seen.some((url) => url.includes("api.goldsky.com") && url.includes("delphi-testnet/")), true);
  assert.equal(reply.ok, true);
});

test("legacy settlement reads winner rows, and an unclaimed market does not", async () => {
  const market = "0xda34528f" + "11".repeat(16);
  const legacy = "0x7b8fdbd187b0be5e30e48b1995df574a62667147";
  const hash = "0x" + "ab".repeat(32);
  const reply = await handle(
    {
      op: "subgraph_settlement",
      args: { market_address: market, first: 5 },
      network: "testnet",
      max_outbound: 2,
    },
    async () => ({
      status: 200,
      ok: true,
      json: async () => ({
        data: {
          gatewayWinnerSubmitteds: [{
            id: "win-1", block_number: "1", timestamp_: "2",
            transactionHash_: hash, contractId_: "c1",
            marketProxy: market, winningOutcomeIdx: "1",
          }],
        },
      }),
    }),
    () => ({
      disposable: "",
      client: {
        resolveGateway: async () => legacy,
        getSubgraphUrl: () => (
          "https://api.goldsky.com/api/public/project_x/subgraphs/delphi-testnet-autoset/1.0.0/gn"
        ),
        getSubgraph() { throw new Error("automated subgraph was used"); },
      },
    }),
  );
  assert.equal(reply.ok, true);
  assert.equal(reply.result.settled[0].winningOutcomeIdx, "1");
  let reads = 0;
  const unclaimed = () => ({
    disposable: "",
    client: {
      resolveGateway: async () => {
        reads += 1;
        if (reads > 1) await fetch("https://gensyn-testnet.g.alchemy.com/reread");
        return "0x1111111111111111111111111111111111111111";
      },
      getSubgraph() { throw new Error("unclaimed market was read"); },
    },
  });
  const empty = await handle(
    {
      op: "subgraph_settlement",
      args: { market_address: market, first: 5 },
      network: "testnet",
      max_outbound: 2,
    },
    async (input) => {
      if (String(input).includes("/reread")) return { status: 200, ok: true, json: async () => ({}) };
      throw new Error("subgraph fetch should not run");
    },
    unclaimed,
  );
  assert.equal(empty.ok, false);
  assert.equal(empty.error_type, "unsupported_market");
  reads = 0;
  const trades = await handle(
    {
      op: "subgraph_trades",
      args: { market_address: market, first: 5, skip: 0 },
      network: "testnet",
      max_outbound: 2,
    },
    async (input) => {
      if (String(input).includes("/reread")) return { status: 200, ok: true, json: async () => ({}) };
      throw new Error("subgraph fetch should not run");
    },
    unclaimed,
  );
  assert.equal(trades.ok, false);
  assert.equal(trades.error_type, "unsupported_market");
});
