graph TD
    A[Identify Coding Issue/Error] --> B{Understand Error Message & Context};
    B --> C{Analyze Code Logic & Syntax};
    C --> D{"Check Common Issues (Typos, Dependencies, Environment)"};
    %% <- Text enclosed in quotes
    D --> E{Search Internal Knowledge/Training Data};
    E --> F{Issue Resolved?};
    F -- Yes --> G[Solution Found & Verified];
    F -- No --> H{Formulate Query for Another AI};
    H --> I[Send Query to Assisting AI];
    I --> J{Receive & Evaluate Suggestion};
    J --> K{Implement Suggested Solution};
    K --> L{Test Implementation};
    L --> M{Issue Resolved?};
    M -- Yes --> G;
    M -- No --> N[Escalate/Report Unresolved Issue];
    G --> O[End Process];
    N --> O;

    style A fill:#f9f,stroke:#333,stroke-width:2px
    style O fill:#f9f,stroke:#333,stroke-width:2px
    style F fill:#ccf,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5
    style M fill:#ccf,stroke:#333,stroke-width:2px,stroke-dasharray: 5 5
    style H fill:#fcc,stroke:#333,stroke-width:2px
    style I fill:#fcc,stroke:#333,stroke-width:2px
    style J fill:#fcc,stroke:#333,stroke-width:2px
    style G fill:#cfc,stroke:#333,stroke-width:2px
    style N fill:#f99,stroke:#333,stroke-width:2px
```

**Flowchart Explanation:**

 1. **Identify Coding Issue/Error:** The process starts when an error is detected or a coding problem is identified.

 2. **Understand Error Message & Context:** The AI analyzes the specific error message and the surrounding code to understand the nature of the problem.

 3. **Analyze Code Logic & Syntax:** It reviews the code's structure, logic flow, and syntax rules.

 4. **Check Common Issues:** The AI looks for frequent mistakes like typos, missing dependencies, or configuration problems.

 5. **Search Internal Knowledge/Training Data:** It consults its own database and training examples for similar problems and known solutions.

 6. **Issue Resolved? (Decision):** If a solution is found internally, it proceeds to verification.

 7. **Formulate Query for Another AI:** If the issue persists, the AI prepares a clear and concise query describing the problem for another AI model.

 8. **Send Query to Assisting AI:** The query is sent to a designated helper AI.

 9. **Receive & Evaluate Suggestion:** The AI receives the response and assesses its relevance and potential effectiveness.

10. **Implement Suggested Solution:** The proposed fix is applied to the code.

11. **Test Implementation:** The modified code is tested to see if the issue is resolved.

12. **Issue Resolved? (Decision):** Checks if the external suggestion fixed the problem.

13. **Solution Found & Verified:** If the issue is resolved (either internally or via assistance), the process concludes successfully.

14. **Escalate/Report Unresolved Issue:** If neither internal checks nor external assistance resolves the issue, it's flagged for further review or manual intervention.

15. **End Process:** The flowchart conclud
