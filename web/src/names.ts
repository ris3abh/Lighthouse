/** Every name the product uses, from the same file the Python package reads (ADR 0010). */
import names from "../../areao1/core/names.json" with { type: "json" };

export const PRODUCT: string = names.product;
export const WRITE_HEADER: string = names.write_header;
export const REPO: string = names.repo;
