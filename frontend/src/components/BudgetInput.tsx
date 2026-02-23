import { useState, useEffect } from "react";

interface BudgetInputProps {
    budget: number;
    fee: number;
    onBudgetChange: (budget: number) => void;
    onFeeChange: (fee: number) => void;
}

export function BudgetInput({
    budget,
    fee,
    onBudgetChange,
    onFeeChange,
}: BudgetInputProps) {
    const [budgetStr, setBudgetStr] = useState(budget.toString());
    const [feeStr, setFeeStr] = useState((fee * 100).toFixed(1));

    useEffect(() => {
        setBudgetStr(budget.toString());
    }, [budget]);

    const handleBudgetBlur = () => {
        const val = parseFloat(budgetStr);
        if (!isNaN(val) && val > 0) {
            onBudgetChange(val);
        } else {
            setBudgetStr(budget.toString());
        }
    };

    const handleFeeBlur = () => {
        const val = parseFloat(feeStr);
        if (!isNaN(val) && val >= 0) {
            onFeeChange(val / 100);
        } else {
            setFeeStr((fee * 100).toFixed(1));
        }
    };

    const handleBudgetKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter") handleBudgetBlur();
    };

    const handleFeeKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter") handleFeeBlur();
    };

    return (
        <div className="budget-bar">
            <div className="budget-field">
                <label htmlFor="budget-input">Budget</label>
                <div className="input-with-prefix">
                    <span className="prefix">$</span>
                    <input
                        id="budget-input"
                        type="text"
                        inputMode="decimal"
                        value={budgetStr}
                        onChange={(e) => setBudgetStr(e.target.value)}
                        onBlur={handleBudgetBlur}
                        onKeyDown={handleBudgetKeyDown}
                        placeholder="100"
                    />
                </div>
            </div>
            <div className="budget-field fee-field">
                <label htmlFor="fee-input">Fee / contract</label>
                <div className="input-with-suffix">
                    <input
                        id="fee-input"
                        type="text"
                        inputMode="decimal"
                        value={feeStr}
                        onChange={(e) => setFeeStr(e.target.value)}
                        onBlur={handleFeeBlur}
                        onKeyDown={handleFeeKeyDown}
                        placeholder="1.1"
                    />
                    <span className="suffix">¢</span>
                </div>
            </div>
        </div>
    );
}
