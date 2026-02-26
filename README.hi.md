<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/code-batch/readme.png" alt="CodeBatch" width="400">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/code-batch/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/code-batch/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/code-batch/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

सामग्री-आधारित बैच निष्पादन इंजन, जिसमें नियतात्मक विभाजन (deterministic sharding) और क्वेरी करने योग्य आउटपुट होते हैं।

**यह क्या है:** यह एक फ़ाइल सिस्टम-आधारित निष्पादन ढांचा है जो कोड की स्नैपशॉट लेता है, कार्यों को नियतात्मक रूप से विभाजित करता है, और संरचित प्रश्नों के लिए प्रत्येक आउटपुट को अनुक्रमित करता है—किसी डेटाबेस की आवश्यकता नहीं है।

**यह किसके लिए है:** उन डेवलपर्स के लिए जो दोहराने योग्य कोड विश्लेषण पाइपलाइन, CI एकीकरण, या बैच रूपांतरण वर्कफ़्लो बना रहे हैं, जिन्हें पुनरुत्पादकता और ऑडिट क्षमता की आवश्यकता होती है।

**यह कैसे अलग है:** प्रत्येक इनपुट सामग्री-आधारित होता है और प्रत्येक निष्पादन नियतात्मक होता है। छह महीने बाद भी उसी बैच को फिर से चलाएं और आपको समान परिणाम मिलेंगे। लॉग को पार्स किए बिना, सिमेंटिक प्रकार के आधार पर आउटपुट को क्वेरी करें।

## अवलोकन

CodeBatch कोडबेस पर नियतात्मक रूपांतरण चलाने के लिए एक फ़ाइल सिस्टम-आधारित निष्पादन ढांचा प्रदान करता है। यह इनपुट को अपरिवर्तनीय स्नैपशॉट के रूप में कैप्चर करता है, कार्यों को अलग-अलग खंडों में निष्पादित करता है, और कुशल क्वेरी के लिए सभी सिमेंटिक आउटपुट को अनुक्रमित करता है—बिना किसी डेटाबेस की आवश्यकता के।

## दस्तावेज़

- **[SPEC.md](./SPEC.md)** — पूर्ण भंडारण और निष्पादन विनिर्देश
- **[docs/TASKS.md](./docs/TASKS.md)** — कार्य संदर्भ (पार्स, विश्लेषण, प्रतीक, लिंट)
- **[CHANGELOG.md](./CHANGELOG.md)** — संस्करण इतिहास

## त्वरित शुरुआत

```bash
# Initialize a store
codebatch init ./store

# Create a snapshot of a directory
codebatch snapshot ./my-project --store ./store

# List available pipelines
codebatch pipelines

# Initialize a batch with a pipeline
codebatch batch init --snapshot <id> --pipeline full --store ./store

# Run all tasks and shards (Phase 5 workflow)
codebatch run --batch <id> --store ./store

# View progress
codebatch status --batch <id> --store ./store

# View summary
codebatch summary --batch <id> --store ./store
```

## मानव कार्यप्रवाह (चरण 5)

चरण 5 में मानव-अनुकूल कमांड जोड़े गए हैं जो मौजूदा बुनियादी तत्वों को जोड़ते हैं:

```bash
# Run entire batch (no manual shard iteration needed)
codebatch run --batch <id> --store ./store

# Resume interrupted execution
codebatch resume --batch <id> --store ./store

# Progress summary
codebatch status --batch <id> --store ./store

# Output summary
codebatch summary --batch <id> --store ./store
```

## खोज क्षमता

```bash
# List pipelines
codebatch pipelines

# Show pipeline details
codebatch pipeline full

# List tasks in a batch
codebatch tasks --batch <id> --store ./store

# List shards for a task
codebatch shards --batch <id> --task 01_parse --store ./store
```

## क्वेरी उपनाम

```bash
# Show errors
codebatch errors --batch <id> --store ./store

# List files in a snapshot
codebatch files --batch <id> --store ./store

# Top output kinds
codebatch top --batch <id> --store ./store
```

## अन्वेषण और तुलना (चरण 6)

चरण 6 में आउटपुट का पता लगाने और बैचों की तुलना करने के लिए केवल-पढ़ने योग्य दृश्य जोड़े गए हैं—बिना स्टोर को बदले।

```bash
# Inspect all outputs for a file
codebatch inspect src/main.py --batch <id> --store ./store

# Compare two batches
codebatch diff <batchA> <batchB> --store ./store

# Show regressions (new/worsened diagnostics)
codebatch regressions <batchA> <batchB> --store ./store

# Show improvements (fixed/improved diagnostics)
codebatch improvements <batchA> <batchB> --store ./store

# Explain data sources for any command
codebatch inspect src/main.py --batch <id> --store ./store --explain
```

## निम्न-स्तरीय कमांड

बारीक नियंत्रण के लिए, मूल कमांड उपलब्ध रहते हैं:

```bash
# Run a specific shard
codebatch run-shard --batch <id> --task 01_parse --shard ab --store ./store

# Query outputs
codebatch query outputs --batch <id> --task 01_parse --store ./store

# Query diagnostics
codebatch query diagnostics --batch <id> --task 01_parse --store ./store

# Build LMDB acceleration cache
codebatch index-build --batch <id> --store ./store
```

## विशिष्ट संस्करण

यह विनिर्देश सिमेंटिक संस्करण का उपयोग करता है, जिसमें ड्राफ्ट/स्थिर मार्कर होते हैं। प्रत्येक संस्करण को गिट में टैग किया जाता है (उदाहरण के लिए, `spec-v1.0-draft`)। महत्वपूर्ण परिवर्तन प्रमुख संस्करण को बढ़ाते हैं। कार्यान्वयन को यह घोषित करना चाहिए कि वे किस विशिष्ट संस्करण को लक्षित करते हैं और आगे की अनुकूलता के लिए अज्ञात फ़ील्ड को सहन करते हैं।

## परियोजना संरचना

```
schemas/      JSON Schema definitions for all record types
src/          Core implementation
tests/        Test suites and fixtures
docs/         Documentation
.github/      CI/CD workflows
```

## समर्थन

- **प्रश्न / सहायता:** [चर्चाएँ](https://github.com/mcp-tool-shop-org/code-batch/discussions)
- **बग रिपोर्ट:** [समस्याएँ](https://github.com/mcp-tool-shop-org/code-batch/issues)

## लाइसेंस

MIT
