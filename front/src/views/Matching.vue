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
                <th >Current Vocabulary Term</th>
                <th>
                  <div class="th-header-inner">
                    <div class="th-header-top">
                      <span>New Term (Your Vocabulary)</span>
                      <select
                        v-model="ontologyMode"
                        @change="onOntologyModeChange"
                        class="ontology-select"
                      >
                        <option value="USKB">USKB (schema.org)</option>
                        <option value="manual">Manual</option>
                        <option v-for="v in userVocabularies" :key="v.id" :value="`user_vocab:${v.id}`">
                          {{ v.title || v.url }}
                        </option>
                        <option value="url">Add from URL...</option>
                      </select>
                    </div>
                    <div
                      v-if="ontologyMode === 'url'"
                      class="add-url-wrapper"
                    >
                      <input
                        v-model="ontologyUrl"
                        type="text"
                        class="new_term add-url-input"
                        placeholder="Enter ontology URL"
                      />
                      <button
                        type="button"
                        class="add-url-btn"
                        @click="onAddFromUrl"
                      >
                        Add
                      </button>
                    </div>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in filteredProperties" :key="p.uri">
                <td class="text-dim">{{ p.original_label }}</td>
                <td>
                  <input
                    v-model="p.mapped_label"
                    :list="ontologyMode==='USKB' ? 'uskb-suggestions' : (isUserVocabMode ? 'url-suggestions' : null)"
                    @input="onTermInput(p)"
                    :placeholder="ontologyMode === 'USKB'
                      ? `Enter or select new Term for '${p.original_label}'`
                      : ontologyMode === 'url'
                        ? `Enter or select label from URL for '${p.original_label}'`
                        : `Enter label or URI for '${p.original_label}'`"
                    class="new_term"
                  />
                </td>
              </tr>
            </tbody>
          </table>
          <datalist id="uskb-suggestions">
            <option v-for="t in uskbTerms" :key="t.uri" :value="t.label" />
          </datalist>
          <datalist id="url-suggestions">
            <option v-for="t in urlTerms" :key="t.uri" :value="t.label" />
          </datalist>
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
      ontologyMode: "USKB",   
      uskbTerms: [],          
      uskbLoading: false,
      ontologyUrl: "",
      urlTerms: [],
      urlLoading: false,
      userVocabularies: [],
      loadingUserVocabularies: false,
    };
  },
  watch: {
  ontologyUrl(newVal) {
    if (!newVal || newVal.trim() === "") {
      this.urlTerms = [];
    }
  }
},
  async mounted() {
    axios.defaults.withCredentials = true;
    axios.defaults.xsrfCookieName = "csrftoken";
    axios.defaults.xsrfHeaderName = "X-CSRFToken";
    await this.loadDatasets();
    await this.loadUserVocabularies();
    this.loadUSKBSuggestions();
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
    isUserVocabMode() {
      return typeof this.ontologyMode === "string" && this.ontologyMode.startsWith("user_vocab:");
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
      this.ontologyUrl = "";
      this.urlTerms = [];
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
          const value = p.mapped_uri || p.mapped_label || "";
          return {
            uri: p.uri,
            original_label: p.original_label,
            mapped_label: value,
            mapped_uri: p.mapped_uri ,
            display_label: p.display_label,
            _initial_mapped_label: value, 
          };
        });
      } catch (e) {
        console.error("properties error:", e);
        this.error = "Failed to load properties.";
      } finally {
        this.loading = false;
      }
    },
    async loadUserVocabularies() {
      this.loadingUserVocabularies = true;
      try {
        const { data } = await axios.get("/api/vocabulary/user/", { withCredentials: true });
        this.userVocabularies = data?.vocabularies || [];
      } catch (e) {
        console.error("Load user vocabularies failed:", e);
        this.userVocabularies = [];
      } finally {
        this.loadingUserVocabularies = false;
      }
    },

    async saveMappings() {
      if (!this.selectedDataset) return;

      const changed = this.properties.filter(
        p => (p.mapped_label ?? "") !== (p._initial_mapped_label ?? "")
      );
      if (changed.length === 0) return;

        const items = changed.map(p => {
          let newLabel = (p.mapped_label ?? "").trim();
          if (this.isUserVocabMode && p.mapped_uri) {
            newLabel = p.mapped_uri;
          }
          const obj = {
            original_uri: p.uri,
            new_label: newLabel,
            source: p.mapped_source || "manual",
          };
          return obj;
        });

      this.saving = true;
      this.error = "";
      try {
        const { data } = await axios.post("/api/matching/mappings/", {
          dataset: this.selectedDataset,
          items,
        }, { withCredentials: true });

        await this.loadProperties(this.selectedDataset);

        const saved = data?.saved ?? 0;
        const deleted = data?.deleted ?? 0;

        let msg = "";
        if (saved > 0 && deleted > 0) {
          msg = `${saved} mapping${saved === 1 ? "" : "s"} saved and ${deleted} deleted successfully.`;
        } else if (saved > 0) {
          msg = `${saved} mapping${saved === 1 ? "" : "s"} saved successfully.`;
        } else if (deleted > 0) {
          msg = `${deleted} mapping${deleted === 1 ? "" : "s"} deleted successfully.`;
        }
        if (msg) alert(msg);
      } catch (e) {
        console.error("save mappings error:", e);
        this.error = "Failed to save mappings.";
      } finally {
        this.saving = false;
      }
    },
    async loadUSKBSuggestions(q = "", kind = "property") {
      this.uskbLoading = true;
      try {
        const { data } = await axios.get("/api/vocabulary/uskb/", {
          params: { kind, limit: 2000, q },
          withCredentials: true,
    });
        this.uskbTerms = data?.terms || [];
      } catch (e) {
        console.error("Load USKB failed:", e);
        this.uskbTerms = [];
      } finally {
        this.uskbLoading = false;
      }
    },
    async onAddFromUrl() {
      const url = (this.ontologyUrl || "").trim();
      if (!url) {
        alert("Please enter an ontology URL first.");
        return;
      }

      this.urlLoading = true;
      try {
        const { data } = await axios.get("/api/vocabulary/external/", {
          params: { url },
          withCredentials: true,
        });

        this.urlTerms = data?.terms || [];

        if (!this.urlTerms.length) {
          alert("No terms found for this URL.");
        }
        const saved = await axios.post(
          "/api/vocabulary/user/",
          { url },
          { withCredentials: true }
        );
        const savedVocab = saved.data;

        const exists = this.userVocabularies.some(v => v.id === savedVocab.id);
          if (!exists) {
            this.userVocabularies.push({
              id: savedVocab.id,
              title: savedVocab.title,
              url: savedVocab.url,
          });
        }
        this.ontologyMode = `user_vocab:${savedVocab.id}`;
        this.ontologyUrl = "";
      } catch (e) {
        console.error("Load URL vocabulary failed:", e);
        this.urlTerms = [];
        alert("Failed to fetch vocabulary terms from the given URL.");
      } finally {
        this.urlLoading = false;
      }
    },

    async onOntologyModeChange() {
      if (this.ontologyMode === "url") {
        this.ontologyUrl = "";
        this.urlTerms = [];
        return;
      }
      if (this.ontologyMode === "USKB" && this.uskbTerms.length === 0) {
        this.loadUSKBSuggestions();
      }
      if (this.isUserVocabMode) {
        const id = Number(this.ontologyMode.split(":")[1]);
        const v = this.userVocabularies.find(x => x.id === id);
        if (!v) return;

        this.ontologyUrl = v.url; 

        this.urlLoading = true;
        try {
          const { data } = await axios.get("/api/vocabulary/external/", {
            params: { url: v.url },
            withCredentials: true,
          });
          this.urlTerms = data?.terms || [];
          console.log(
            "mode:", this.ontologyMode,
            "urlTerms:", this.urlTerms?.length
          );
        } catch (e) {
          console.error("Load saved vocabulary terms failed:", e);
          this.urlTerms = [];
          alert("Failed to fetch terms for saved vocabulary.");
        } finally {
          this.urlLoading = false;
        }

        return;
      }
    },

    onTermInput(p) {
      if (this.ontologyMode === "USKB") {
        const t = this.uskbTerms.find(x => x.label === p.mapped_label);
        p.mapped_uri = t ? t.uri : null;
        p.mapped_source = t ? "schema.org" : "manual";
        return;
      }
      if (this.isUserVocabMode) {
        const typed = (p.mapped_label || "").trim().toLowerCase();
        const t = this.urlTerms.find(x => (x.label || "").trim().toLowerCase() === typed);
        p.mapped_uri = t ? t.uri : null;     
        p.mapped_source = t ? "url" : "manual";
        return;
      }
      p.mapped_uri = null;
      p.mapped_source = "manual";
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
  width: 90%;
  max-width: none;
  margin: 0 auto;
}

.matching-header {
  padding: 1.5rem 2rem;
  border-bottom: 1px solid #e5e7eb;
  h2 {
    font-size: 1.25rem;
    font-weight: 600;
    color: #232711;
  }
  p {
    font-size: 0.9rem;
    color: #6b7280;
    margin-top: 0.3rem;
  }
}

.matching-filters {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  padding: 1.5rem 2rem;
  background-color: #fafafa;
  border-bottom: 1px solid #e5e7eb;

  .filter-item {
    display: flex;
    flex-direction: column;

    label {  
      font-size: 0.85rem;
      color: #374151;
      margin-bottom: 0.4rem;
      font-weight: 700;
    }

    select,
    input {
      padding: 0.5rem 0.75rem;
      border: 1px solid #d1d5db;
      border-radius: 6px;
      font-size: 0.9rem;
      color: #111827;

      &:focus {
        outline: none;
        border-color: #dc2626;
        box-shadow: 0 0 0 1px #dc2626;
      }
    }
  }
}

.matching-table {
  padding: 2rem;

  .empty-message {
    text-align: center;
    color: #6b7280;
  }
}

.prop-table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;

  th,
  td {
    padding: 16px 14px;
    border-bottom: 1px solid #f0f2f5;
    text-align: left;
    vertical-align: middle;
    font-family: inherit;
    font-size: 0.9rem;
    color: #4B5563;
  }

  thead th {
    background: #fafafa;
    font-weight: 600;
  }

  thead th:first-child {
    width: 50%;
  }

  tbody tr:hover {
    background: #fcfcfd;
  }

  tbody td {
    color: #000;
    font-weight: 500;
  }

  thead th:last-child .th-header-inner {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  thead th:last-child .th-header-top {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  thead th:last-child .th-header-top span {
    flex: 1;
    font-size: 0.95rem;
    font-weight: 600;
    color: #4B5563;
  }

  thead th:last-child .add-url-input {
    width: 500px ; 
    height: 26px ;
  }

  thead th:last-child .add-url-wrapper {
    display: flex;
    align-items: center;
    gap: 0.75rem;  
  } 

  thead th:last-child select {
    font: inherit;
    color: inherit;
    padding: 0.25rem 0.4rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    background: #fff;
  }

  thead th:last-child select:focus {
    outline: none;
    border-color: #dc2626;
    box-shadow: 0 0 0 1px #dc2626;
  }
}

.new_term {
  width: 500px;
  padding: 12px 14px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 500;
  color: #000;
  font-family: inherit;
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
  display: flex;
  justify-content: flex-end;

  button {
    background-color: #dc2626;
    color: white;
    font-weight: 600;
    padding: 0.5rem 1.5rem;
    border-radius: 6px;
    border: none;
    cursor: pointer;
    transition: opacity 0.15s ease;
  }

  button.is-disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}
input::placeholder {
  font-family: inherit;
  font-size: 0.9rem;
  font-weight: 500;
  color: #9CA3AF; 
}
</style>
