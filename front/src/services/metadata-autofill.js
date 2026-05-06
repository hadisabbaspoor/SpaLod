import { queryables } from "./constants";

const SKIP_AUTOFILL_FIELDS = ["catalog", "title", "publisher"];

function text(node) {
  return node?.textContent?.trim() || "";
}

function exactLocalName(node) {
  return (node.localName || node.nodeName.split(":").pop()).toLowerCase();
}

function valuesByExactFieldName(doc, key) {
  const normalizedKey = key.toLowerCase();
  const values = [];

  for (const node of doc.getElementsByTagName("*")) {
    if (exactLocalName(node) !== normalizedKey) continue;

    const value = text(node);
    if (value && !values.includes(value)) {
      values.push(value);
    }
  }

  return values;
}

export async function extractMetadataFromXml(file) {
  const xmlText = await file.text();
  const xmlDoc = new DOMParser().parseFromString(xmlText, "text/xml");

  if (xmlDoc.querySelector("parsererror")) {
    throw new Error("Invalid XML file.");
  }

  const result = {};

  for (const field of queryables) {
    const key = field.q;

    if (!key) continue;
    if (SKIP_AUTOFILL_FIELDS.includes(key)) continue;

    const values = valuesByExactFieldName(xmlDoc, key);
    const value = values.join(", ");

    if (value) {
      result[key] = value;
    }
  }

  return result;
}