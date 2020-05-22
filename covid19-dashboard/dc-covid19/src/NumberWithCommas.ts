/**
 * Converts a number to a comma-separated number.
 * Example, 10000 gets converted to 10,000
 * @param num
 */
export default function numberWithCommas(num: number) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",")
}
