export interface Market {
    error: string | null;
}
export interface ListMarketsResponse {
    markets: Market[] | null;
}
export interface ListPositionsResponse {
    positions: Position[] | null;
}
