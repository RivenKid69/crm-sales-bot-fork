import { Entity, PrimaryGeneratedColumn, Column, CreateDateColumn, UpdateDateColumn, DeleteDateColumn } from 'typeorm';

@Entity('ugd_licenses')
export class UgdLicenseDao {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  ugds_id: number;

  @Column()
  dgds_id: number;

  @Column()
  license_number: string;

  @Column({
    type: 'varchar',
    length: 12,
  })
  bin: string;

  @Column()
  status: string;

  @Column({ name: 'options', type: 'jsonb' })
  options: string;

  @Column()
  wholesale_address: string;

  @Column()
  source: string;

  @CreateDateColumn()
  created_at: Date;

  @UpdateDateColumn()
  updated_at: Date;

  @DeleteDateColumn({ name: 'deleted_at' })
  deleted_at: Date;
}
