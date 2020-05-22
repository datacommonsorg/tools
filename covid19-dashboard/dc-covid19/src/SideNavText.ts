/**
 * Returns the SideNav links with its subsections.
 * @constructor
 */
export default function SideNavText() {
    return [
        [   {"daily": "Daily"},
            {"dailyPerCapita": "Daily Per Capita"},
            {"dailyIncrease": "Daily Increase"}
        ],
        [
            {"weekly": "Weekly"},
            {"weeklyPerCapita": "Weekly Per Capita"},
            {"weeklyIncrease": "Weekly Increase"}
        ],
        [
            {"monthly": "Monthly"},
            {"monthlyPerCapita": "Monthly Per Capita"},
            {"monthlyIncrease": "Monthly Increase"}
        ],
        [
            {"absoluteCumulative": "Cumulative"},
            {"cumulativePerCapita": "Cumulative Per Capita"}
        ]
        ]
}