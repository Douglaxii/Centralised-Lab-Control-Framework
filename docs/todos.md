applets:
    laser alignment assist
    trap centre finder/DAC calibration
    uv3 resonant frequency calibration

flask:
    applets interface:
        display design:
            auto compensation:
                output: 
                    pos_y vs comp_h
                    PMT vs comp_v
                input:
                    ec1
                    ec2

            camp_sweep:
                output:
                    sigx, R_y, PMT vs frequency
                input:
                    tartget freq
                    freq span
                    data points
                    att
                    on time
                    off time

            sim_calibration:
                output:
                    result table
                input:
                    u_rf start
                    u_rf finish
                    u_rf datapoints
                    v_end start
                    v_end finish
                    v_end datapoints

    BO interface:

project:
    toptica control:
        Bephi
        UV3

    e_gun alignment:
        oscilloscope connection
        auto alignment

ARTIQ:
    migration:
        u_rf
        piezo
        hd_valve
        b_field
        e_gun
        be_oven
        bephi
        uv3
        pressure sensor
    
