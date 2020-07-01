import moment from 'moment';

export default class IsoDate {
  date;

  constructor(isoDate: string) {
    this.date = moment(isoDate);
  }

  /**
   * Adds or subtracts any number of days to an ISO date.
   * For example, 2020-01-07 minus 2 days would return 2020-01-05.
   * NOTE: You can pass in negative or positive days accordingly.
   * @param days: either positive or negative days to add
   */
  addDays = (days: number): string => {
    // Make a deep copy of this date, we will add/subtract from it.
    const date = this.date.clone();

    if (days < 0) {
      // Subtracting to date
      date.subtract(Math.abs(days), 'days');
    } else {
      // Adding to date
      date.add(Math.abs(days), 'days');
    }

    return date.format('YYYY-MM-DD');
  };

  /**
   * Given an array of deltaDays, compute the real isoDates.
   * For example, isoDate = 2020-01-10 and deltaDays = [0, 1, 7]
   * Returns an array with the ISODates [2020-01-10, 2020-01-09, 2020-01-03]
   * 0 represents today, 1 represents 1 day ago, and 7 represents 7 days ago.
   * @param deltaDays: list of numbers to subtract days from.
   */
  getDatesFromDeltaDays = (deltaDays: number[]): string[] => {
    const dates = deltaDays.map(deltaDate => this.addDays(-deltaDate));
    return dates.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  };

  /**
   * Returns an array containing [initialDate, lastDate]
   * For example, if we cared about the data from 01-01-10 to 1 week ago.
   * initialDate = 2020-01-10, deltaDays = 7, returns [2020-01-03, 2020-01-10]
   * @param deltaDays: number of days before our isoDate to look at
   */
  makeRange = (deltaDays: number): [string, string] => {
    // [isoDate - deltaDays, isoDate]
    return [this.addDays(-deltaDays), this.toIso()];
  };

  toIso = () => {
    return this.date.format('YYYY-MM-DD');
  };
}
