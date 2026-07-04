const state = {
  timeframes: [],
  strategies: [],
  selectedTimeframes: [],
  selectedStrategies: [],
  filters: [
    { field: "win_rate", op: ">=", value: "65" },
    { field: "profit_factor", op: ">=", value: "1.2" },
  ],
  filterFields: [],
  operators: [],
  mode: "normal",
  columns: [],
  rows: [],
  columnVisibility: {},
  fontSize: 13,
  searchText: "",
  loading: false,
  sortCol: null,
  sortDir: "asc",
  rowSelect: {},
  ratings: {},
};

function setState(updates) {
  Object.assign(state, updates);
}
