CREATE MIGRATION m1mm67jkrk5gvvtrjzqhmup2ilspnfm4s6vmeoed7x5nexlxxk3tmq
    ONTO m1vtisyimxhdhd2vnavathbzofihze4na6xdaqnymyytqlsafxqt5a
{
  ALTER TYPE default::User {
      ALTER PROPERTY email {
          RESET OPTIONALITY;
      };
  };
};
