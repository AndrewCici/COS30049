### Table 1. In-distribution (grouped split, balanced per source and label)

| Model | Features | Scaled | Unit | Sent. precision | Sent. recall | Sent. F1 | Sent. AUC | Brier | Human FPR | Essay F1 | Essay AUC | Fit (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Logistic Regression | sparse | no | unit | 0.886 | 0.924 | 0.905 | 0.965 | 0.074 | 0.124 | 0.964 | 0.987 | 4.8 |
| k-NN (k=25) | dense | yes | unit | 0.725 | 0.815 | 0.767 | 0.836 | 0.170 | 0.323 | 0.881 | 0.958 | 0.4 |
| Decision Tree | dense | no | unit | 0.714 | 0.699 | 0.706 | 0.764 | 0.206 | 0.292 | 0.846 | 0.914 | 6.8 |
| Random Forest | dense | no | unit | 0.801 | 0.765 | 0.782 | 0.860 | 0.162 | 0.199 | 0.887 | 0.956 | 23.0 |
| SVM (RBF) | dense | yes | unit | 0.821 | 0.795 | 0.808 | 0.888 | 0.135 | 0.181 | 0.924 | 0.973 | 49.2 |
| XGBoost | sparse | no | beyond-unit | 0.860 | 0.918 | 0.888 | 0.956 | 0.085 | 0.156 | 0.957 | 0.988 | 68.7 |
| RoBERTa detector (pretrained; 8000 sentences per class) | n/a | n/a | beyond-unit | 0.757 | 0.901 | 0.823 | 0.905 | 0.183 | 0.302 | - | - | - |

### Table 2. Cross-source generalisation (train on one corpus, test on the other)

| Model | DAIGT_v2->HC3 P | DAIGT_v2->HC3 R | DAIGT_v2->HC3 F1 | DAIGT_v2->HC3 AUC | HC3->DAIGT_v2 P | HC3->DAIGT_v2 R | HC3->DAIGT_v2 F1 | HC3->DAIGT_v2 AUC | Mean cross AUC | AUC gap |
|---|---|---|---|---|---|---|---|---|---|---|
| Logistic Regression | 0.768 | 0.610 | 0.680 | 0.790 | 0.548 | 0.863 | 0.670 | 0.676 | 0.733 | 0.233 |
| k-NN (k=25) | 0.633 | 0.708 | 0.668 | 0.689 | 0.625 | 0.467 | 0.534 | 0.627 | 0.658 | 0.178 |
| Decision Tree | 0.635 | 0.518 | 0.571 | 0.620 | 0.583 | 0.502 | 0.539 | 0.597 | 0.609 | 0.155 |
| Random Forest | 0.679 | 0.535 | 0.599 | 0.676 | 0.628 | 0.489 | 0.550 | 0.625 | 0.651 | 0.210 |
| SVM (RBF) | 0.719 | 0.520 | 0.604 | 0.701 | 0.648 | 0.524 | 0.580 | 0.668 | 0.684 | 0.204 |
| XGBoost | 0.878 | 0.574 | 0.694 | 0.873 | 0.517 | 0.878 | 0.651 | 0.596 | 0.734 | 0.221 |

### Table 3. In-distribution test sentences by source

| Model | DAIGT_v2 P | DAIGT_v2 R | DAIGT_v2 F1 | DAIGT_v2 AUC | HC3 P | HC3 R | HC3 F1 | HC3 AUC |
|---|---|---|---|---|---|---|---|---|
| Logistic Regression | 0.856 | 0.909 | 0.882 | 0.954 | 0.922 | 0.941 | 0.931 | 0.976 |
| k-NN (k=25) | 0.705 | 0.831 | 0.762 | 0.838 | 0.751 | 0.797 | 0.773 | 0.837 |
| Decision Tree | 0.718 | 0.712 | 0.715 | 0.777 | 0.709 | 0.684 | 0.696 | 0.747 |
| Random Forest | 0.802 | 0.783 | 0.793 | 0.875 | 0.799 | 0.744 | 0.770 | 0.841 |
| SVM (RBF) | 0.823 | 0.811 | 0.817 | 0.900 | 0.819 | 0.777 | 0.797 | 0.875 |
| XGBoost | 0.815 | 0.900 | 0.855 | 0.934 | 0.918 | 0.939 | 0.928 | 0.976 |
| RoBERTa detector (pretrained) | 0.614 | 0.825 | 0.704 | 0.754 | 0.979 | 0.989 | 0.984 | 0.999 |
