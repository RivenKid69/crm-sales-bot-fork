import { Column, CreateDateColumn, Entity, OneToMany, PrimaryGeneratedColumn, UpdateDateColumn } from 'typeorm';
import { GeoNodeToLicensesDao } from './geo-node_licenses.dao';

@Entity('licenses')
export class LicenseDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column({ unique: true })
  license_number: string;

  @Column()
  status: string;

  @Column({ type: 'jsonb' })
  options: any;

  @CreateDateColumn({ name: 'created_at' })
  created_at: Date;

  @UpdateDateColumn({ name: 'updated_at' })
  updated_at: Date;

  @OneToMany(() => GeoNodeToLicensesDao, (geoNodeLicenses) => geoNodeLicenses.license)
  geoNodeLicenses: GeoNodeToLicensesDao[];
}
