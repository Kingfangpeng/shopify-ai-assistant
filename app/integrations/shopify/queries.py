"""Shopify Admin GraphQL 2026-07 read-only query documents."""

SHOP_STATUS_QUERY = """
query ShopStatus {
  shop { name myshopifyDomain currencyCode }
  currentAppInstallation { accessScopes { handle } }
}
"""

ORDERS_SUMMARY_QUERY = """
query OrdersSummary($first: Int!, $after: String, $query: String!) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    nodes {
      id
      cancelledAt
      currentTotalPriceSet { shopMoney { amount currencyCode } }
      totalRefundedSet { shopMoney { amount currencyCode } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

ABANDONED_CHECKOUTS_QUERY = """
query AbandonedCheckouts($first: Int!, $after: String, $query: String!) {
  abandonedCheckouts(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    nodes {
      id
      createdAt
      completedAt
      totalPriceSet { shopMoney { amount currencyCode } }
      lineItems(first: 100) { nodes { quantity title } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

INVENTORY_QUERY = """
query Inventory($first: Int!, $after: String) {
  productVariants(first: $first, after: $after, sortKey: ID) {
    nodes {
      id
      title
      sku
      inventoryQuantity
      product { id title }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

PRODUCT_PERFORMANCE_QUERY = """
query ProductPerformance($first: Int!, $after: String, $query: String!) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    nodes {
      lineItems(first: 250) {
        nodes {
          quantity
          currentQuantity
          discountedTotalSet { shopMoney { amount currencyCode } }
          product { id title }
        }
      }
      refunds {
        refundLineItems(first: 100) {
          nodes { quantity lineItem { product { id } } }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

CUSTOMER_SEGMENTS_QUERY = """
query CustomerSegments($first: Int!, $after: String, $query: String!) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    nodes {
      id
      customer { id numberOfOrders }
      billingAddress { countryCodeV2 }
      currentTotalPriceSet { shopMoney { amount currencyCode } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

REFUNDS_QUERY = """
query Refunds($first: Int!, $after: String, $query: String!) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    nodes {
      id
      currentTotalPriceSet { shopMoney { amount currencyCode } }
      refunds {
        id
        createdAt
        totalRefundedSet { shopMoney { amount currencyCode } }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

DISCOUNTS_QUERY = """
query DiscountPerformance($first: Int!, $after: String, $query: String!) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    nodes {
      id
      discountCodes
      currentTotalPriceSet { shopMoney { amount currencyCode } }
      totalDiscountsSet { shopMoney { amount currencyCode } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""

ORDER_LIST_QUERY = """
query OrderList($first: Int!, $after: String, $query: String!) {
  orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT, reverse: true) {
    nodes {
      id
      name
      createdAt
      displayFinancialStatus
      displayFulfillmentStatus
      cancelledAt
      billingAddress { countryCodeV2 }
      currentTotalPriceSet { shopMoney { amount currencyCode } }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""
