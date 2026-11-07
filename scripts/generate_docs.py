"""Write three FAKE documents for the GenAI part: two bank policies and one call-centre transcript.

Run from the project folder:   python scripts/generate_docs.py
Creates:  data/raw/docs/*.txt

The documents deliberately contain fake personal data (a phone number, an email, an ID number),
so we can prove the pipeline removes it before the text is stored for search.
"""
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "docs"

DOCUMENTS = {
    "kyc_procedure.txt": (
        "KYC and customer due diligence procedure. Every new retail customer must be identified before an "
        "account is opened. Staff verify the customer's identity using an original national ID or passport and "
        "record the document number in the onboarding system. Proof of address such as a utility bill not older "
        "than three months is required. All customers are screened against sanctions lists and politically exposed "
        "persons registers. Customers are assigned a risk rating of low, medium or high; high risk customers "
        "require enhanced due diligence and approval by the compliance officer. Identity documents and risk "
        "ratings are refreshed every two years for high risk customers and every five years otherwise. "
        "Questions go to the compliance team at kyc.team@examplebank.co.ke or on 0700123456. Suspicious "
        "activity must be reported to the money laundering reporting officer without tipping off the customer.\n"
    ),
    "loan_policy.txt": (
        "Salary advance and personal loan policy. A customer is eligible for a salary advance if their salary "
        "has been credited to the bank account for at least three consecutive months and the account is active. "
        "The maximum advance is fifty percent of net monthly salary. A credit reference bureau check is mandatory "
        "before any loan is approved, and customers with active defaults listed at the CRB are declined. Interest "
        "is charged as a flat monthly rate disclosed in the loan agreement before disbursement. Repayment is "
        "deducted automatically on the next salary date. When a repayment is missed the loan moves to arrears "
        "after one day and the customer receives an SMS reminder; after thirty days the case is escalated to the "
        "collections team and reported to the credit reference bureau as non performing.\n"
    ),
    "call_transcript_0042.txt": (
        "Call transcript 0042, contact centre. Agent: Thank you for calling, how can I help? Customer: My M-Pesa "
        "transfer from my savings account failed but the money left my account. Agent: I am sorry about that. To "
        "verify you, please confirm your ID No 23456789 and the phone number registered on the account. Customer: "
        "It is 0722111222. Agent: Thank you. I can see the failed transfer to the paybill. Failed M-Pesa transfers "
        "are reversed automatically within forty eight hours. If the reversal does not appear after that time I "
        "will raise a transaction dispute and you will get an SMS confirmation. Customer: Okay, that is fine. "
        "Agent: Is there anything else? Customer: No, thank you.\n"
    ),
}

DOCS_DIR.mkdir(parents=True, exist_ok=True)
for name, text in DOCUMENTS.items():
    (DOCS_DIR / name).write_text(text, encoding="utf-8")
print(f"Wrote {len(DOCUMENTS)} documents to {DOCS_DIR}")