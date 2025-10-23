<template>
  <div class="matching-page">
    <div class="matching-card">
      <div class="matching-header">
        <h2>Vocabulary Update</h2>
        <p>Map your new terms to the current vocabulary. Leave a field blank to keep the original term.</p>
      </div>

      <div class="matching-filters">
        <!-- Dataset Selector -->
        <div class="filter-item">
          <label>Dataset</label>
          <select v-model="selectedDataset" @change="onDatasetChange">
            <option value="">-- Select a Dataset --</option>
            <option v-for="d in datasets" :key="d.iri" :value="d.iri">
              {{ d.label || d.iri }}
            </option>
          </select>
        </div>

        <!-- Search Box -->
        <div class="filter-item">
          <label>Search Term</label>
          <input
            v-model="search"
            type="text"
            placeholder="Filter results..."
          />
        </div>
      </div>

      <div class="matching-table">

        <div v-if="!selectedDataset" class="empty-message">
          Please select a Dataset to begin.
        </div>

        <div v-else-if="loading" class="empty-message">Loading properties…</div>

        <div v-else-if="error" class="empty-message" style="color:#dc2626;">
          {{ error }}
        </div>

        <div v-else>
          <div v-if="filteredProperties.length === 0" class="empty-message">
            No properties found.
          </div>

          <table v-else class="prop-table">
            <thead>
              <tr>
                <th style="width:50%">Current Vocabulary Term</th>
                <th>New Term (Your Vocabulary)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in filteredProperties" :key="p.uri">
                <td class="mono text-dim">{{ p.original_label }}</td>
                <td>
                  <input
                    v-model="p.mapped_label"
                    class="new_term"
                    :placeholder="`Enter new term for '${p.original_label}'`"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="matching-footer">
        <button
          :disabled="saving || !selectedDataset || dirtyCount === 0"
          @click="saveMappings"
          :class="{ 'is-disabled': saving || !selectedDataset || dirtyCount === 0 }"
        >
          {{ saving ? 'Saving…' : `Update Vocabulary (${dirtyCount})` }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import axios from "axios";

export default {
  name: "Matching",
  data() {
    return {
      datasets: [],
      selectedDataset: "",
      search: "",
      properties: [],
      loading: false,
      error: "",
      saving: false,
    };
  },
  async mounted() {
    axios.defaults.withCredentials = true;
    axios.defaults.xsrfCookieName = "csrftoken";
    axios.defaults.xsrfHeaderName = "X-CSRFToken";
    await this.loadDatasets();
  },
  computed: {
    filteredProperties() {
      const q = (this.search || "").toLowerCase().trim();
      if (!q) return this.properties;
      return this.properties.filter(
        (p) =>
          (p.display_label || "").toLowerCase().includes(q) ||
          (p.original_label || "").toLowerCase().includes(q) ||
          (p.mapped_label || "").toLowerCase().includes(q)
      );
    },

    dirtyCount() {
      return this.properties.filter(p => (p.mapped_label ?? "") !== (p._initial_mapped_label ?? "")).length;
    },
  },
  methods: {
    async loadDatasets() {
      try {
        const { data } = await axios.get("/api/matching/datasets/");
        this.datasets = data.datasets || [];
      } catch (e) {
        console.error("datasets error:", e);
        this.datasets = [];
      }
    },

    async onDatasetChange() {
      this.search = "";
      this.properties = [];
      this.error = "";
      if (!this.selectedDataset) return;
      await this.loadProperties(this.selectedDataset);
    },

    async loadProperties(datasetIri) {
      this.loading = true;
      this.error = "";
      try {
        const { data } = await axios.get("/api/matching/properties/", {
          params: { dataset: datasetIri },
          withCredentials: true,
        });

        this.properties = (data.properties || []).map((p) => {
          const mapped = p.mapped_label || ""; 
          return {
            uri: p.uri,
            original_label: p.original_label,
            mapped_label: mapped,
            display_label: p.display_label,
            _initial_mapped_label: mapped, 
          };
        });
      } catch (e) {
        console.error("properties error:", e);
        this.error = "Failed to load properties.";
      } finally {
        this.loading = false;
      }
    },

    async saveMappings() {
      if (!this.selectedDataset) return;

      const changed = this.properties.filter(
        p => (p.mapped_label ?? "") !== (p._initial_mapped_label ?? "")
      );

      const items = changed.map(p => ({
        original_uri: p.uri,
        new_label: (p.mapped_label ?? "").trim(), 
      }));

      if (items.length === 0) return;

      this.saving = true;
      this.error = "";
      try {
        const { data } = await axios.post("/api/matching/mappings/", {
          dataset: this.selectedDataset,
          items,
        }, { withCredentials: true });

        await this.loadProperties(this.selectedDataset);

        alert(`Saved ${data?.saved ?? items.length} mappings successfully.`);
      } catch (e) {
        console.error("save mappings error:", e);
        this.error = "Failed to save mappings.";
      } finally {
        this.saving = false;
      }
    },
  },
};
</script>

<style lang="scss" scoped>

.matching-page {
  padding: 1.5rem;
  background-color: #f8fafc;
  min-height: 100vh;
  width: 100%;
  box-sizing: border-box;
}
.matching-card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
  border: 1px solid #e5e7eb;
  width: 100%;
  max-width: none;
  margin: 0;
}
.matching-header {
  padding: 1.5rem 2rem;
  border-bottom: 1px solid #e5e7eb;
  h2 { font-size: 1.25rem; font-weight: 600; color: #111827; }
  p  { font-size: 0.9rem;  color: #6b7280;  margin-top: 0.3rem; }
}
.matching-filters {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  padding: 1.5rem 2rem;
  background-color: #fafafa;
  border-bottom: 1px solid #e5e7eb;

  .filter-item {
    display: flex; flex-direction: column;
    label { font-size: 0.85rem; color: #374151; margin-bottom: 0.4rem; }
    select, input {
      padding: 0.5rem 0.75rem;
      border: 1px solid #d1d5db; border-radius: 6px; font-size: 0.9rem; color: #111827;
      &:focus { outline: none; border-color: #dc2626; box-shadow: 0 0 0 1px #dc2626; }
    }
  }
}
.matching-table {
  padding: 2rem;
  .empty-message { text-align: center; color: #6b7280; }
}
.prop-table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;

  th, td {
    padding: 16px 14px;
    border-bottom: 1px solid #f0f2f5;
    text-align: left;
    vertical-align: middle;
  }
  thead th {
    background: #fafafa;
    font-weight: 600;
    color: #374151;
    font-size: 0.9rem;
  }
  tbody tr:hover { background: #fcfcfd; }

  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .text-dim { color: #000000; }
}
.new_term {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 0.9rem;
}
.new_term:focus {
  outline: none;
  border-color: #dc2626;
  box-shadow: 0 0 0 1px #dc2626;
}
.matching-footer {
  padding: 1.5rem 2rem;
  background-color: #f9fafb;
  border-top: 1px solid #e5e7eb;
  display: flex; justify-content: flex-end;
  button {
    background-color: #dc2626; color: white; font-weight: 600;
    padding: 0.5rem 1.5rem; border-radius: 6px; border: none;
    cursor: pointer;
    transition: opacity .15s ease;
  }
  button.is-disabled { opacity: 0.6; cursor: not-allowed; }
}
</style>
