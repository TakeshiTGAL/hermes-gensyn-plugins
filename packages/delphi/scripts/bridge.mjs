import { randomBytes } from "node:crypto";
import { DelphiClient, SubgraphClient } from "@gensyn-ai/gensyn-delphi-sdk";
import { pathToFileURL } from "node:url";
const API_HOSTS = new Set(["api.delphi.fyi", "delphi-api.gensyn.ai"]);
const READ_HOSTS = new Set([
  ...API_HOSTS, "api.goldsky.com",
  "gensyn-testnet.g.alchemy.com", "gensyn-mainnet.g.alchemy.com",
]);
const PRICED = new Set(["quote_buy", "quote_sell", "live_edge"]);
const KEYED = new Set(["list_markets", "get_market", "get_positions", "live_edge"]);
const SIGNED = new Set([...PRICED, "subgraph_trades", "subgraph_settlement"]);
const LEGACY = {
  testnet: "0x7b8fdbd187b0be5e30e48b1995df574a62667147",
  mainnet: "0x4e4e85c52e0f414cc67ee88d0c649ec81698d700",
};
const HTTP_PREFIX = /^(?:API request failed|Subgraph request failed|Health check failed) \(([1-5][0-9]{2})\)/;
const OPS = new Set([
  "list_markets", "get_market", "get_positions", "subgraph_meta", "subgraph_trades",
  "subgraph_settlement", "quote_buy", "quote_sell", "live_edge",
]);
function coded(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}
function chain(error) {
  const out = [];
  const seen = new Set();
  let cur = error;
  while (cur && typeof cur === "object" && !seen.has(cur) && out.length < 8) {
    seen.add(cur)
    out.push(cur)
    cur = cur.cause
  }
  return out;
}
export function httpStatus(error) {
  for (const item of chain(error)) {
    if (Number.isInteger(item.status) && item.status >= 100 && item.status <= 599) return item.status;
  }
  const match = HTTP_PREFIX.exec(String(error?.message ?? ""));
  return match ? Number(match[1]) : 0;
}
function named(error, part) {
  return chain(error).some((item) => String(item.name || "").includes(part));
}
function rpcLimited(error) { return chain(error).some((item) => item.code === 429); }
export function classifyError(error, op = "") {
  const code = error?.code;
  if (code === "lmsr_probability") return "unsupported_market";
  if (code === "unsupported_market" || code === "invalid_response" || code === "config") return code;
  const status = httpStatus(error);
  if (status === 429 || rpcLimited(error)) return "rate_limited";
  if (status === 404) return String(op).startsWith("subgraph_") ? "unsupported_market" : "not_found";
  if (status === 401 || status === 403) return KEYED.has(op) ? "auth" : "upstream";
  if (named(error, "Timeout") || named(error, "Abort")) return "timeout";
  if (named(error, "Revert") && PRICED.has(op)) return "market_not_quotable";
  if (error instanceof SyntaxError) return "invalid_response";
  return "upstream";
}
export function numberText(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    throw coded("invalid_response", "implied probability is outside the unit interval");
  }
  return String(value);
}
const FAILURES = {
  auth: "The API key was refused.", rate_limited: "The rate limit was reached.",
  upstream: "The upstream read failed.", timeout: "The read timed out.",
  invalid_response: "The response had the wrong shape.",
  invalid_argument: "The arguments did not match.",
  config: "The local configuration is incomplete.", internal: "The local adapter failed.",
  market_not_quotable: "The market could not be quoted.",
  not_found: "The market is not in the API list.",
  unsupported_market: "This market's history is not readable by this tool.",
};
export function fixedMessage(kind, status = "") {
  const sentence = FAILURES[kind] || FAILURES.upstream;
  return /^[1-5][0-9]{2}$/.test(status) ? `${sentence} (${status})` : sentence;
}
function decodeOnce(text, pattern) {
  return text.replace(pattern, (_, hex) => {
    const code = Number.parseInt(hex, 16);
    return code <= 0x10FFFF ? String.fromCodePoint(code) : "";
  });
}
export function holdsSecret(text, secret) {
  const needle = String(secret || "").toLowerCase();
  if (!needle) return false;
  const pieces = [needle];
  for (let i = 0; i <= needle.length - 12; i += 1) {
    pieces.push(needle.slice(i, i + 12));
  }
  const raw = String(text ?? "");
  const percent = decodeOnce(raw, /%([0-9A-Fa-f]{2})/g);
  const unicode = decodeOnce(raw, /\\u([0-9A-Fa-f]{4})/g);
  const forms = [raw, percent, unicode, decodeOnce(percent, /\\u([0-9A-Fa-f]{4})/g),
    decodeOnce(unicode, /%([0-9A-Fa-f]{2})/g)];
  return forms.some((form) => pieces.some((piece) => form.toLowerCase().includes(piece)));
}
function seal(body, disposable = "") {
  const encoded = JSON.stringify(body);
  const api = process.env.DELPHI_API_ACCESS_KEY || "";
  if (!holdsSecret(encoded, api) && !holdsSecret(encoded, disposable)) return body;
  const note = holdsSecret("failed", api) || holdsSecret("failed", disposable) ? "error" : "failed";
  return { ok: false, error_type: "internal", message: note, outbound: body.outbound ?? 0 };
}
function requestUrl(input) {
  if (typeof input === "string" || input instanceof URL) return new URL(input);
  return new URL(input.url);
}
function guardedInit(url, init) {
  const next = { ...(init ?? {}), redirect: "manual" };
  if (!API_HOSTS.has(url.hostname) && next.headers) {
    const headers = new Headers(next.headers);
    headers.delete("x-api-key");
    next.headers = headers;
  }
  return next;
}
function pageKey(url) {
  const path = url.pathname.replace(/\/+$/, "");
  if (path.endsWith("/markets")) return "markets";
  if (path.endsWith("/positions")) return "positions";
  return "";
}
export function createFetchGate(realFetch, maximum, allowedHosts = null) {
  let outbound = 0;
  const pages = [];
  return {
    pages,
    async fetch(input, init) {
      const url = requestUrl(input);
      if (url.protocol !== "https:") throw new Error("Refusing non-https upstream request");
      if (allowedHosts && !allowedHosts.has(url.hostname)) {
        throw new Error("Refusing request to an unapproved host");
      }
      if (outbound >= maximum) throw new Error("Refusing request beyond reserved outbound budget");
      outbound += 1;
      const response = await realFetch(input, guardedInit(url, init));
      if (response.status >= 300 && response.status < 400) {
        throw new Error("Refusing redirected upstream response");
      }
      const key = pageKey(url);
      if (key && response.ok && typeof response.clone === "function") {
        let body = null;
        try { body = await response.clone().json(); } catch { body = null; }
        const present = !!body && typeof body === "object" && !Array.isArray(body)
          && Object.prototype.hasOwnProperty.call(body, key);
        pages.push(present);
      }
      return response;
    },
    count: () => outbound,
  };
}
function object(value, label) {
  const bad = !value || typeof value !== "object" || Array.isArray(value);
  if (bad) throw new Error(`${label} must be an object`);
  return value;
}
function openClient(network, priced) {
  if (!priced) {
    return { disposable: "", client: new DelphiClient({
      network, apiKey: process.env.DELPHI_API_ACCESS_KEY,
    }) };
  }
  const disposable = `0x${randomBytes(32).toString("hex")}`;
  return { disposable, client: new DelphiClient({
    network, apiKey: process.env.DELPHI_API_ACCESS_KEY,
    signerType: "private_key", privateKey: disposable,
  }) };
}
async function withDecimals(client, amount) {
  const decimals = { status: "unavailable" };
  try {
    const token = await client.getErc20BalanceWithDecimals();
    const value = typeof token.decimals === "bigint" ? Number(token.decimals) : token.decimals;
    if (Number.isInteger(value) && value >= 0 && value <= 255) {
      decimals.status = "known";
      decimals.value = value;
    }
  } catch { decimals.status = "unavailable"; }
  return { amount_raw: amount.toString(), decimals };
}
function legacyUrl(current) {
  const url = new URL(current);
  if (url.hostname !== "api.goldsky.com" || !url.pathname.includes("-autoset/")) {
    throw coded("unsupported_market", "legacy subgraph is outside the approved host");
  }
  url.pathname = url.pathname.replace("-autoset/", "/");
  return url.toString();
}
async function readWinners(subgraph, market, first) {
  const fields = "id block_number timestamp_ transactionHash_ contractId_";
  const head = `{gatewayWinnerSubmitteds(first:${first},orderBy:timestamp_,`;
  const where = `where:{marketProxy:"${market}"}){${fields}`;
  const data = await subgraph.query(`${head}orderDirection:desc,${where} marketProxy winningOutcomeIdx}}`);
  const rows = data.gatewayWinnerSubmitteds;
  if (!Array.isArray(rows)) throw coded("invalid_response", "winner page is missing");
  const settled = rows.map((row) => ({
    ...row, contractId_: row.contractId_ ?? row.id,
    marketCreatorReward: null, refund: null, marketCreatorTradingFeesCut: null,
  }));
  return { settled, failed: [], resolutionRequests: [] };
}
async function readSubgraph(client, network, op, args, reads) {
  if (op === "subgraph_meta") return client.getSubgraph().getMeta();
  const market = String(args.market_address).toLowerCase();
  let gateway = "";
  try { gateway = String(await client.resolveGateway(market)).toLowerCase(); }
  catch { throw coded("unsupported_market", "gateway could not be resolved"); }
  const mid = reads();
  try { await client.resolveGateway(market); }
  catch { throw coded("unsupported_market", "gateway could not be resolved"); }
  if (reads() !== mid) throw coded("unsupported_market", "market is not on a readable factory");
  const legacy = gateway === (LEGACY[network] || "");
  const subgraph = legacy
    ? new SubgraphClient(legacyUrl(client.getSubgraphUrl()), { settlementEconomics: false })
    : client.getSubgraph();
  if (op === "subgraph_trades") {
    return subgraph.getMarketTrades(market, { first: args.first, skip: args.skip });
  }
  if (legacy) return readWinners(subgraph, market, args.first);
  return subgraph.getMarketSettlement(market, { first: args.first });
}
async function quote(client, op, args) {
  const common = { marketAddress: args.market_address, outcomeIdx: args.outcome_idx };
  if (op === "quote_buy") {
    const quoted = await client.quoteBuy({ ...common, sharesOut: BigInt(args.shares_raw) });
    return withDecimals(client, quoted.tokensIn);
  }
  const quoted = await client.quoteSell({ ...common, sharesIn: BigInt(args.shares_raw) });
  return withDecimals(client, quoted.tokensOut);
}
async function execute(client, network, op, args, reads) {
  if (op === "list_markets") return client.listMarkets(args);
  if (op === "get_market") return client.getMarket({ id: args.market_id });
  if (op === "get_positions") return client.listPositions(args);
  if (op.startsWith("subgraph_")) return readSubgraph(client, network, op, args, reads);
  if (op === "quote_buy" || op === "quote_sell") return quote(client, op, args);
  const market = await client.getMarket({ id: args.market_id, pricesAndImpliedProbabilities: true });
  if (market?.metadata?.mechanism_type === "lmsr") throw coded("lmsr_probability", "lmsr");
  const outcomes = market.metadata?.outcomes;
  const probs = market.spotImpliedProbabilities;
  if (!Array.isArray(outcomes) || !Array.isArray(probs)) {
    throw coded("invalid_response", "implied probabilities do not match the outcomes");
  }
  if (outcomes.length > 0 && probs.length === 0) throw coded("upstream", "spot prices were not returned");
  if (outcomes.length !== probs.length) {
    throw coded("invalid_response", "implied probabilities do not match the outcomes");
  }
  const wanted = String(args.market_id ?? "").toLowerCase();
  const got = String(market.id ?? "").toLowerCase();
  if (!wanted || got !== wanted) throw coded("invalid_response", "market ids do not match");
  return { id: got, spotImpliedProbabilities: probs.map(numberText) };
}
export async function handle(input, realFetch = globalThis.fetch.bind(globalThis), factory = openClient) {
  let gate = { count: () => 0 };
  let disposable = "";
  try {
    object(input, "request");
    if (!OPS.has(input.op)) throw new Error("Unsupported bridge operation");
    const args = object(input.args, "args");
    if (!Number.isInteger(input.max_outbound) || input.max_outbound < 0) {
      throw new Error("max_outbound must be a non-negative integer");
    }
    gate = createFetchGate(realFetch, input.max_outbound, READ_HOSTS);
    globalThis.fetch = gate.fetch;
    const opened = factory(input.network, SIGNED.has(input.op));
    disposable = opened.disposable;
    const result = await execute(opened.client, input.network, input.op, args, () => gate.count());
    const paged = input.op === "list_markets" || input.op === "get_positions";
    if (paged && gate.pages?.some((ok) => !ok)) {
      throw coded("invalid_response", "response object has no page");
    }
    return seal({ ok: true, op: input.op, result, outbound: gate.count() }, disposable);
  } catch (error) {
    const status = httpStatus(error);
    const kind = classifyError(error, input?.op);
    const lmsr = error?.code === "lmsr_probability";
    const sentence = lmsr
      ? "This tool does not return a probability for an lmsr market."
      : fixedMessage(kind, status ? String(status) : "");
    return seal({
      ok: false, error_type: kind, message: sentence,
      detail: lmsr ? "lmsr_probability" : undefined,
      http_status: status || undefined, outbound: gate.count(),
    }, disposable);
  } finally { globalThis.fetch = realFetch; }
}
async function main() {
  let response;
  try {
    const chunks = [];
    let size = 0;
    for await (const chunk of process.stdin) {
      size += chunk.length;
      if (size > 65_536) throw new Error("Bridge request is too large");
      chunks.push(chunk);
    }
    response = await handle(JSON.parse(Buffer.concat(chunks).toString("utf8")));
  } catch (error) {
    const kind = error instanceof SyntaxError ? "invalid_argument" : "internal";
    response = seal({ ok: false, error_type: kind, message: fixedMessage(kind), outbound: 0 });
  }
  process.stdout.write(`${JSON.stringify(response)}\n`);
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
