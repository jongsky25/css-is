// Source is the pinned Chromium file identified by manifest.json.
Attr* Element::getAttributeNodeNS(const AtomicString& namespace_uri,
                                  const AtomicString& local_name) {
  if (!HasElementData()) {
    return nullptr;
  }
  QualifiedName q_name(g_null_atom, local_name, namespace_uri);
  SynchronizeAttribute(q_name);
  const Attribute* attribute = GetElementData()->Attributes().Find(q_name);
  if (!attribute) {
    return nullptr;
  }
  return EnsureAttr(attribute->GetName());
}
